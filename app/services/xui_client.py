import logging
import httpx
import json
import uuid
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class XuiClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

class XuiClient:
    """
    Async client wrapper for 3x-ui Panel APIs.
    Supports both API Key (Bearer token) and Basic Auth (session cookie).
    """
    def __init__(
        self,
        base_url: str,
        auth_type: str = "api_key",
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_type = auth_type
        self.api_key = api_key
        self.username = username
        self.password = password
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        # Disable SSL verification for convenience (or customize via config)
        self.client = httpx.AsyncClient(
            verify=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=httpx.Timeout(10.0, connect=3.0)
        )
        await self.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def login(self):
        if not self.client:
            raise XuiClientError("Client not initialized.")
            
        if self.auth_type == "api_key":
            if self.api_key:
                self.client.headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                logger.warning("XUI auth_type is api_key but XUI_API_KEY is not set.")
        elif self.auth_type == "basic_auth":
            if self.username and self.password:
                try:
                    resp = await self.client.post(
                        f"{self.base_url}/login",
                        data={"username": self.username, "password": self.password}
                    )
                    if resp.status_code >= 400:
                        raise XuiClientError(f"Login failed with status {resp.status_code}: {resp.text}", resp.status_code)
                except Exception as e:
                    logger.error("Failed to authenticate with 3x-ui basic_auth", exc_info=e)
                    raise XuiClientError(f"Authentication failed: {str(e)}")
            else:
                logger.warning("XUI auth_type is basic_auth but credentials are not set.")

    async def _request(self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.client:
            raise XuiClientError("Client not initialized. Use async with context manager.")
        
        url = f"{self.base_url}{endpoint}"
        try:
            resp = await self.client.request(method, url, json=json_data, params=params)
            
            # If 401 and using basic_auth, try to re-login once
            if resp.status_code == 401 and self.auth_type == "basic_auth":
                logger.info("Session expired (401), attempting re-login.")
                await self.login()
                resp = await self.client.request(method, url, json=json_data, params=params)
                
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {"success": False, "msg": resp.text}

            if resp.status_code >= 400 or not resp_json.get("success", True):
                msg = resp_json.get("msg") or f"HTTP {resp.status_code}"
                raise XuiClientError(msg, resp.status_code, resp_json)
                
            return resp_json
        except httpx.HTTPError as e:
            logger.error(f"HTTP request to 3x-ui failed: {url}", exc_info=e)
            raise XuiClientError(f"Network error: {str(e)}")

    async def get_inbounds(self) -> List[Dict[str, Any]]:
        resp = await self._request("GET", "/panel/api/inbounds/list")
        return resp.get("obj", [])

    async def get_inbound(self, inbound_id: int) -> Optional[Dict[str, Any]]:
        inbounds = await self.get_inbounds()
        for inbound in inbounds:
            if inbound.get("id") == inbound_id:
                return inbound
        return None

    async def get_client(self, inbound_id: Any, email: str) -> Optional[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
        """
        Returns a tuple of (client settings dict, client stats dict) for a given email.
        """
        try:
            resp = await self._request("GET", f"/panel/api/clients/get/{email}")
            obj = resp.get("obj", {})
            client = obj.get("client")
            if not client:
                return None
            
            up = obj.get("up") or client.get("up") or 0
            down = obj.get("down") or client.get("down") or 0
            c_stat = {"up": up, "down": down}
            return client, c_stat
        except Exception as e:
            logger.warning(f"Failed to get client {email} using new API: {e}")
            return None

    async def get_client_links(self, email: str) -> List[str]:
        """
        Fetches client links directly from the panel.
        """
        try:
            resp = await self._request("GET", f"/panel/api/clients/getLinks/{email}")
            return resp.get("obj", [])
        except Exception as e:
            logger.warning(f"Failed to get client links for {email}: {e}")
            return []

    async def add_client(
        self,
        inbound_ids: Any,
        email: str,
        client_uuid: str,
        limit_ip: int = 0,
        total_gb: int = 0,
        expiry_time: int = 0,
        flow: str = "",
        tg_id: int = 0,
        sub_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if isinstance(inbound_ids, int):
            inbound_ids = [inbound_ids]
        elif not isinstance(inbound_ids, list):
            try:
                inbound_ids = [int(inbound_ids)]
            except Exception:
                inbound_ids = []

        client_data = {
            "id": client_uuid,
            "flow": flow,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_time,
            "enable": True,
            "tgId": tg_id,
            "subId": sub_id or str(uuid.uuid4())[:16]
        }
        
        payload = {
            "client": client_data,
            "inboundIds": inbound_ids
        }
        
        return await self._request("POST", "/panel/api/clients/add", json_data=payload)

    async def update_client(
        self,
        inbound_id: Any,
        client_uuid: str,
        email: str,
        limit_ip: int = 0,
        total_gb: int = 0,
        expiry_time: int = 0,
        enable: bool = True,
        flow: str = "",
        tg_id: Optional[int] = None,
        sub_id: Optional[str] = None
    ) -> Dict[str, Any]:
        current_tg_id = 0
        current_sub_id = None
        current_flow = flow
        
        if email.startswith("usr_"):
            try:
                parts = email.split("_")
                current_tg_id = int(parts[1])
                current_sub_id = email.split("_sub_")[-1]
            except Exception:
                pass
                
        try:
            resp = await self._request("GET", f"/panel/api/clients/get/{email}")
            existing_obj = resp.get("obj", {})
            existing_client = existing_obj.get("client")
            if existing_client:
                current_tg_id = existing_client.get("tgId") or current_tg_id
                current_sub_id = existing_client.get("subId") or current_sub_id
                if not current_flow:
                    current_flow = existing_client.get("flow", "")
        except Exception as e:
            logger.warning(f"Could not retrieve client {email} details before update: {e}")
            
        if tg_id is not None:
            current_tg_id = tg_id
        if sub_id is not None:
            current_sub_id = sub_id
            
        client_data = {
            "id": client_uuid,
            "flow": current_flow,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_time,
            "enable": enable,
            "tgId": current_tg_id,
            "subId": current_sub_id or str(uuid.uuid4())[:16]
        }
        
        return await self._request("POST", f"/panel/api/clients/update/{email}", json_data=client_data)

    async def delete_client(self, inbound_id: Any, client_uuid: str) -> Dict[str, Any]:
        email = client_uuid
        if not ("@" in email or email.startswith("usr_")):
            try:
                all_clients = await self.get_all_clients()
                found = next((c for c in all_clients if c.get("uuid") == client_uuid), None)
                if found:
                    email = found["email"]
            except Exception as e:
                logger.warning(f"Failed to lookup email by uuid {client_uuid} during delete: {e}")
                
        return await self._request("POST", f"/panel/api/clients/del/{email}")

    async def reset_client_traffic(self, inbound_id: Any, email: str) -> Dict[str, Any]:
        return await self._request("POST", f"/panel/api/clients/resetTraffic/{email}")

    async def get_all_clients(self) -> List[Dict[str, Any]]:
        """
        Returns a flat list of all clients on the server.
        """
        try:
            resp = await self._request("GET", "/panel/api/clients/list")
            clients_list = resp.get("obj", [])
            all_clients = []
            for item in clients_list:
                c = item.get("client", {})
                email = c.get("email", "")
                inbound_ids = item.get("inboundIds", [])
                
                up = item.get("up") or c.get("up") or 0
                down = item.get("down") or c.get("down") or 0
                
                all_clients.append({
                    "email": email,
                    "uuid": c.get("id", ""),
                    "tgId": c.get("tgId", ""),
                    "subId": c.get("subId", ""),
                    "enable": c.get("enable", True),
                    "flow": c.get("flow", ""),
                    "limitIp": c.get("limitIp", 0),
                    "totalGB": c.get("totalGB", 0),
                    "expiryTime": c.get("expiryTime", 0),
                    "up": up,
                    "down": down,
                    "inbound_id": inbound_ids[0] if inbound_ids else 0,
                    "inbound_ids": inbound_ids,
                    "inbound_remark": "",
                    "inbound_port": 0,
                    "inbound_protocol": "",
                })
            return all_clients
        except Exception as e:
            logger.warning(f"Failed to fetch clients list from new API: {e}. Falling back to old list parsing.")
            
        inbounds = await self.get_inbounds()
        all_clients = []
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            inbound_remark = inbound.get("remark", "")
            inbound_port = inbound.get("port", 0)
            inbound_protocol = inbound.get("protocol", "")
            
            try:
                settings_raw = json.loads(inbound.get("settings", "{}"))
            except Exception:
                settings_raw = {}
            
            clients = settings_raw.get("clients", [])
            client_stats = inbound.get("clientStats", [])
            stats_map = {s.get("email"): s for s in client_stats}
            
            for c in clients:
                email = c.get("email", "")
                stat = stats_map.get(email, {})
                
                all_clients.append({
                    "email": email,
                    "uuid": c.get("id", ""),
                    "tgId": c.get("tgId", ""),
                    "subId": c.get("subId", ""),
                    "enable": c.get("enable", True),
                    "flow": c.get("flow", ""),
                    "limitIp": c.get("limitIp", 0),
                    "totalGB": c.get("totalGB", 0),
                    "expiryTime": c.get("expiryTime", 0),
                    "up": stat.get("up", 0),
                    "down": stat.get("down", 0),
                    "inbound_id": inbound_id,
                    "inbound_ids": [inbound_id],
                    "inbound_remark": inbound_remark,
                    "inbound_port": inbound_port,
                    "inbound_protocol": inbound_protocol,
                })
        return all_clients

    async def get_system_stats(self) -> Dict[str, Any]:
        return await self._request("GET", "/panel/api/server/status")
