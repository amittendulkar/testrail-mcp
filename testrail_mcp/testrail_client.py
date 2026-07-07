"""TestRail API client module."""
import base64
import json
from typing import Dict, List, Any, Optional, Union
import requests

class TestRailClient:
    """TestRail API client for interacting with TestRail."""

    def __init__(self, base_url: str, username: str, api_key: str):
        """
        Initialize the TestRail API client.
        
        Args:
            base_url: The URL of your TestRail instance (e.g., [https://example.testrail.io/)](https://example.testrail.io/))
            username: Your TestRail username/email
            api_key: Your TestRail API key
        """
        self.username = username
        self.api_key = api_key
        
        # Ensure the base URL ends with a slash
        if not base_url.endswith('/'):
            base_url += '/'
        self.base_url = base_url + 'index.php?/api/v2/'
        
        # Set up the session with authentication
        self.session = requests.Session()
        auth = str(
            base64.b64encode(
                bytes(f'{username}:{api_key}', 'utf-8')
            ),
            'ascii'
        ).strip()
        self.session.headers.update({
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/json',
        })

    def _send_request(self, method: str, uri: str, data: Optional[Dict] = None) -> Any:
        """
        Send a request to the TestRail API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            uri: API endpoint URI
            data: Request data for POST/PUT requests
            
        Returns:
            Response data from TestRail
            
        Raises:
            Exception: If the request fails
        """
        url = self.base_url + uri
        
        if method.upper() == 'GET':
            response = self.session.get(url)
        elif method.upper() == 'POST':
            response = self.session.post(url, data=json.dumps(data) if data else None)
        elif method.upper() == 'PUT':
            response = self.session.put(url, data=json.dumps(data) if data else None)
        elif method.upper() == 'DELETE':
            response = self.session.delete(url)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
            
        if response.status_code >= 300:
            try:
                error = response.json()
            except:
                error = response.text
            raise Exception(f"TestRail API returned HTTP {response.status_code}: {error}")
            
        return response.json() if response.content else {}

    def _send_request_raw(self, method: str, uri: str) -> requests.Response:
        """
        Send a request and return the raw response (for binary downloads).

        Args:
            method: HTTP method (GET)
            uri: API endpoint URI

        Returns:
            Raw requests.Response object

        Raises:
            Exception: If the request fails
        """
        url = self.base_url + uri
        response = self.session.get(url)

        if response.status_code >= 300:
            try:
                error = response.json()
            except:
                error = response.text
            raise Exception(f"TestRail API returned HTTP {response.status_code}: {error}")

        return response

    @staticmethod
    def _extract_next_uri(next_link: str) -> Optional[str]:
        """
        Turn a TestRail `_links.next` value into a base_url-relative URI.

        `base_url` already ends with `index.php?/api/v2/`, so the leading `/api/v2/` from
        the next link must be stripped before appending. If the `api/v2/` marker is absent
        (clean-URL installs / proxy path rewrites), the link is un-parseable in this context;
        return None to STOP rather than build a malformed URL and loop on a bad page.
        """
        marker = 'api/v2/'
        idx = next_link.lower().find(marker)
        if idx == -1:
            return None
        return next_link[idx + len(marker):].lstrip('/')

    def _get_paginated(self, uri: str, entity_key: str, max_pages: int = 1000) -> Dict:
        """
        Fetch ALL pages of a paginated TestRail bulk-API GET endpoint.

        Handles both response shapes:
          * bulk API (recent TestRail): {offset, limit, size, _links:{next}, <entity_key>:[...]}
          * legacy bare list:           [ ... ]

        Returns a normalized dict: {entity_key: [all items], "size": <total>}.
        """
        items: List[Dict] = []
        # Request an explicit page size so behaviour is deterministic across TestRail
        # versions/config and the offset arithmetic in `_links.next` is predictable.
        next_uri: Optional[str] = uri if 'limit=' in uri else f'{uri}&limit=250'
        prev_uri: Optional[str] = None
        pages = 0

        while next_uri and pages < max_pages:
            # Offset-monotonicity guard: if the derived next link does not advance, stop
            # after one extra request instead of hammering the same page `max_pages` times.
            if next_uri == prev_uri:
                break
            pages += 1
            resp = self._send_request('GET', next_uri)
            prev_uri = next_uri

            # Legacy TestRail returned a bare list (no pagination envelope). An empty
            # response (`{}`) yields items=[] with no `_links` and breaks cleanly below.
            if isinstance(resp, list):
                items.extend(resp)
                break
            if not isinstance(resp, dict):
                break

            items.extend(resp.get(entity_key, []) or [])

            nxt = (resp.get('_links') or {}).get('next')
            if not nxt:
                break
            # '/api/v2/get_cases/137&limit=250&offset=250' -> 'get_cases/137&limit=250&offset=250'
            next_uri = self._extract_next_uri(nxt)

        return {entity_key: items, "size": len(items)}

    # Cases API
    def get_case(self, case_id: int) -> Dict:
        """Get a test case by ID."""
        return self._send_request('GET', f'get_case/{case_id}')
    
    def get_cases(self, project_id: int, suite_id: Optional[int] = None,
                  section_id: Optional[int] = None) -> Dict:
        """Get ALL test cases for a project/suite (auto-paginated). Optional section_id filter."""
        uri = f'get_cases/{project_id}'
        if suite_id:
            uri += f'&suite_id={suite_id}'
        if section_id:
            uri += f'&section_id={section_id}'
        return self._get_paginated(uri, 'cases')
    
    def add_case(self, section_id: int, data: Dict) -> Dict:
        """Add a new test case."""
        return self._send_request('POST', f'add_case/{section_id}', data)
    
    def update_case(self, case_id: int, data: Dict) -> Dict:
        """Update an existing test case."""
        return self._send_request('POST', f'update_case/{case_id}', data)
    
    def delete_case(self, case_id: int) -> Dict:
        """Delete a test case."""
        return self._send_request('POST', f'delete_case/{case_id}')
    
    # Projects API
    def get_project(self, project_id: int) -> Dict:
        """Get a project by ID."""
        return self._send_request('GET', f'get_project/{project_id}')
    
    def get_projects(self) -> Dict:
        """Get ALL projects (auto-paginated)."""
        return self._get_paginated('get_projects', 'projects')
    
    def add_project(self, data: Dict) -> Dict:
        """Add a new project."""
        return self._send_request('POST', 'add_project', data)
    
    def update_project(self, project_id: int, data: Dict) -> Dict:
        """Update an existing project."""
        return self._send_request('POST', f'update_project/{project_id}', data)
    
    def delete_project(self, project_id: int) -> Dict:
        """Delete a project."""
        return self._send_request('POST', f'delete_project/{project_id}')
    
    # Runs API
    def get_run(self, run_id: int) -> Dict:
        """Get a test run by ID."""
        return self._send_request('GET', f'get_run/{run_id}')
    
    def get_runs(self, project_id: int) -> List[Dict]:
        """Get all test runs for a project."""
        return self._send_request('GET', f'get_runs/{project_id}')
    
    def add_run(self, project_id: int, data: Dict) -> Dict:
        """Add a new test run."""
        return self._send_request('POST', f'add_run/{project_id}', data)
    
    def update_run(self, run_id: int, data: Dict) -> Dict:
        """Update an existing test run."""
        return self._send_request('POST', f'update_run/{run_id}', data)
    
    def close_run(self, run_id: int) -> Dict:
        """Close a test run."""
        return self._send_request('POST', f'close_run/{run_id}')
    
    def delete_run(self, run_id: int) -> Dict:
        """Delete a test run."""
        return self._send_request('POST', f'delete_run/{run_id}')
    
    # Tests API
    def get_tests(self, run_id: int) -> List[Dict]:
        """Get all tests for a run."""
        return self._send_request('GET', f'get_tests/{run_id}')

    # Results API
    def get_results(self, test_id: int) -> List[Dict]:
        """Get all results for a test."""
        return self._send_request('GET', f'get_results/{test_id}')
    
    def get_results_for_run(self, run_id: int) -> List[Dict]:
        """Get all results for a run."""
        return self._send_request('GET', f'get_results_for_run/{run_id}')
    
    def add_result(self, test_id: int, data: Dict) -> Dict:
        """Add a new result for a test."""
        return self._send_request('POST', f'add_result/{test_id}', data)
    
    def add_results(self, run_id: int, data: Dict) -> List[Dict]:
        """Add multiple results for a run."""
        return self._send_request('POST', f'add_results/{run_id}', data)
    
    def add_results_for_cases(self, run_id: int, data: Dict) -> List[Dict]:
        """Add results for specific cases in a run."""
        return self._send_request('POST', f'add_results_for_cases/{run_id}', data)
    
    # Datasets API (assuming TestRail has dataset endpoints)
    def get_datasets(self, project_id: int) -> List[Dict]:
        """Get all datasets for a project."""
        return self._send_request('GET', f'get_datasets/{project_id}')
    
    def get_dataset(self, dataset_id: int) -> Dict:
        """Get a dataset by ID."""
        return self._send_request('GET', f'get_dataset/{dataset_id}')
    
    def add_dataset(self, project_id: int, data: Dict) -> Dict:
        """Add a new dataset."""
        return self._send_request('POST', f'add_dataset/{project_id}', data)
    
    def update_dataset(self, dataset_id: int, data: Dict) -> Dict:
        """Update an existing dataset."""
        return self._send_request('POST', f'update_dataset/{dataset_id}', data)
    
    def delete_dataset(self, dataset_id: int) -> Dict:
        """Delete a dataset."""
        return self._send_request('POST', f'delete_dataset/{dataset_id}')

    # Sections API
    def get_section(self, section_id:int) -> Dict:
        """Get a specific section"""
        return self._send_request('GET', f'get_section/{section_id}')

    def get_sections(self, project_id: int, suite_id: Optional[int] = None) -> Dict:
        """Get ALL sections for a project/suite (auto-paginated)."""
        uri = f'get_sections/{project_id}'
        if suite_id:
            uri += f'&suite_id={suite_id}'
        return self._get_paginated(uri, 'sections')

    def add_section(self, project_id:int, data:Dict) -> Dict:
        """Add a new section"""
        return self._send_request('POST', f'add_section/{project_id}', data)

    def update_section(self, section_id:int, data:Dict) -> Dict:
        """Update an existing section"""
        return self._send_request('POST', f'update_section/{section_id}', data)

    def delete_section(self, section_id:int, soft:bool) -> Dict:
        """Delete an existing section"""
        url = f'delete_section/{section_id}'
        if (soft):
            url = f'delete_section/{section_id}?soft=1'
        return self._send_request('POST', url)

    def move_section(self, section_id:int, data: Dict) -> Dict:
        """Move a section to a different parent or position"""
        return self._send_request('POST', f'move_section/{section_id}', data)

    # Attachments API
    def get_attachments_for_case(self, case_id: int, limit: Optional[int] = None, offset: Optional[int] = None) -> Dict:
        """Get all attachments for a test case."""
        uri = f'get_attachments_for_case/{case_id}'
        params = []
        if limit is not None:
            params.append(f'limit={limit}')
        if offset is not None:
            params.append(f'offset={offset}')
        if params:
            uri += '&' + '&'.join(params)
        return self._send_request('GET', uri)

    def get_attachment(self, attachment_id: str) -> Dict:
        """Download an attachment by ID. Returns base64-encoded content."""
        response = self._send_request_raw('GET', f'get_attachment/{attachment_id}')
        return {
            'data': base64.b64encode(response.content).decode('ascii'),
            'content_type': response.headers.get('Content-Type', 'application/octet-stream'),
        }
