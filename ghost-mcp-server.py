from typing import Any, Dict, List, Optional
import httpx
import json
import time
import jwt
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
load_dotenv()

# Get configuration from environment variables
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 8053))
GHOST_ADMIN_API_KEY = os.environ.get("GHOST_ADMIN_API_KEY")
GHOST_BASE_URL = os.environ.get("GHOST_BASE_URL")

# Initialize FastMCP server
mcp = FastMCP(
    "ghost",
    host=HOST,
    port=PORT
)

# Ghost API Configuration
# The base URL should not include the API path
GHOST_API_VERSION = "v4"

async def make_ghost_request(endpoint: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make a request to the Ghost Admin API with proper error handling."""
    # Construct the full URL with the API version
    url = f"{GHOST_BASE_URL}/ghost/api/{GHOST_API_VERSION}/admin/{endpoint}"
    
    # Parse the API key into ID and SECRET parts
    key_parts = GHOST_ADMIN_API_KEY.split(':')
    if len(key_parts) != 2:
        return {"error": "Invalid API key format. Expected 'ID:SECRET'"}
    
    id_part, secret_part = key_parts
    
    # Generate JWT token for Ghost Admin API authentication
    iat = int(time.time())
    exp = iat + 300  # 5 minutes expiration
    
    payload = {
        "iat": iat,
        "exp": exp,
        "aud": f"/{GHOST_API_VERSION}/admin/"
    }
    
    jwt_headers = {
        "alg": "HS256",
        "typ": "JWT",
        "kid": id_part
    }
    
    try:
        token = jwt.encode(
            payload,
            bytes.fromhex(secret_part),
            algorithm="HS256",
            headers=jwt_headers
        )
    except Exception as e:
        return {"error": f"Failed to generate JWT token: {str(e)}"}
    
    # Set headers with JWT token
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
        "Accept-Version": GHOST_API_VERSION
    }
    
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, timeout=30.0)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data, timeout=30.0)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, json=data, timeout=30.0)
            else:
                return {"error": f"Unsupported method: {method}"}
                
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"{e}",
                "status_code": e.response.status_code,
                "url": str(e.request.url),
                "headers": dict(e.request.headers),
                "response_text": e.response.text
            }
        except Exception as e:
            return {"error": str(e)}

@mcp.tool()
async def create_post(title: str, content: str, status: str = "draft", tags: Optional[List[str]] = None) -> str:
    """Create a new post in Ghost.
    
    Args:
        title: The title of the post
        content: The content/body of the post in HTML format
        status: Post status (draft, published, scheduled)
        tags: Optional list of tags to associate with the post
    """
    # Prepare the post data
    post_data = {
        "posts": [{
            "title": title,
            "html": content,
            "status": status
        }]
    }
    
    # Add tags if provided
    if tags:
        post_data["posts"][0]["tags"] = [{
            "name": tag
        } for tag in tags]
    
    # Make the API request
    # Add source=html query parameter to ensure proper HTML content handling
    response = await make_ghost_request("posts/?source=html", method="POST", data=post_data)
    
    if "error" in response:
        return f"Error creating post: {response['error']}"
    
    # Extract relevant information from the response
    try:
        post = response["posts"][0]
        return json.dumps({
            "id": post["id"],
            "title": post["title"],
            "url": post["url"],
            "status": post["status"],
            "created_at": post["created_at"]
        }, indent=2)
    except (KeyError, IndexError):
        return f"Unexpected response format: {json.dumps(response)}"

@mcp.tool()
async def debug_api_connection() -> str:
    """Debug the Ghost API connection to help diagnose issues."""
    # Try a simple request to the API root
    async with httpx.AsyncClient() as client:
        try:
            # Test the site URL first
            site_response = await client.get(f"{GHOST_BASE_URL}/ghost/", timeout=30.0)
            
            # Extract ID and SECRET from the API key for debugging
            key_parts = GHOST_ADMIN_API_KEY.split(':')
            if len(key_parts) != 2:
                return {"error": "Invalid API key format. Expected 'ID:SECRET'"}
            
            id_part, secret_part = key_parts
            
            # Generate JWT token for Ghost Admin API authentication
            iat = int(time.time())
            exp = iat + 300  # 5 minutes expiration
            
            payload = {
                "iat": iat,
                "exp": exp,
                "aud": f"/{GHOST_API_VERSION}/admin/"
            }
            
            jwt_headers = {
                "alg": "HS256",
                "typ": "JWT",
                "kid": id_part
            }
            
            try:
                token = jwt.encode(
                    payload,
                    bytes.fromhex(secret_part),
                    algorithm="HS256",
                    headers=jwt_headers
                )
            except Exception as e:
                return json.dumps({"error": f"Failed to generate JWT token: {str(e)}"}, indent=2)
            
            # Set headers with JWT token
            headers = {
                "Authorization": f"Ghost {token}",
                "Content-Type": "application/json",
                "Accept-Version": GHOST_API_VERSION
            }
            
            # Try the site endpoint which should be more accessible
            api_url = f"{GHOST_BASE_URL}/ghost/api/{GHOST_API_VERSION}/admin/site/"
            api_response = await client.get(
                api_url, 
                headers=headers, 
                timeout=30.0
            )
            
            return json.dumps({
                "site_status": site_response.status_code,
                "site_url": str(site_response.url),
                "api_status": api_response.status_code,
                "api_url": str(api_response.url),
                "api_response": api_response.text[:500] if len(api_response.text) > 500 else api_response.text,
                "headers_sent": dict(headers)
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": str(e),
                "api_url": GHOST_ADMIN_API_URL,
                "api_key_format": "ID:SECRET" if len(key_parts) == 2 else "Invalid"
            }, indent=2)

@mcp.tool()
async def list_posts(limit: int = 10, status: str = "all") -> str:
    """List posts from Ghost.
    
    Args:
        limit: Maximum number of posts to retrieve (default: 10)
        status: Filter by post status (all, draft, published, scheduled)
    """
    # Prepare query parameters
    endpoint = f"posts/?source=html&limit={limit}"
    if status != "all":
        endpoint += f"&filter=status:{status}"
    
    # Make the API request
    response = await make_ghost_request(endpoint)
    
    if "error" in response:
        return f"Error listing posts: {response['error']}"
    
    # Format the response
    try:
        posts = response["posts"]
        if not posts:
            return "No posts found matching the criteria."
        
        result = []
        for post in posts:
            result.append({
                "id": post["id"],
                "title": post["title"],
                "status": post["status"],
                "created_at": post["created_at"],
                "updated_at": post["updated_at"]
            })
        
        return json.dumps(result, indent=2)
    except (KeyError, IndexError):
        return f"Unexpected response format: {json.dumps(response)}"

@mcp.tool()
async def edit_post(post_id: str, title: Optional[str] = None, content: Optional[str] = None, 
                 status: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
    """Edit an existing post in Ghost.
    
    Args:
        post_id: The ID of the post to edit
        title: New title for the post (optional)
        content: New content/body for the post in HTML format (optional)
        status: New post status (draft, published, scheduled) (optional)
        tags: New list of tags to associate with the post (optional)
    """
    # First, get the current post data
    current_post = await make_ghost_request(f"posts/{post_id}/?source=html")
    
    if "error" in current_post:
        return f"Error retrieving post: {current_post['error']}"
    
    try:
        # Extract the current post data
        post = current_post["posts"][0]
        
        # Prepare the updated post data
        post_data = {
            "posts": [{
                "id": post_id,
                "title": title if title is not None else post["title"],
                "html": content if content is not None else post["html"],
                "status": status if status is not None else post["status"],
                "updated_at": post["updated_at"]  # Required for version control
            }]
        }
        
        # Add tags if provided
        if tags:
            post_data["posts"][0]["tags"] = [{
                "name": tag
            } for tag in tags]
        
        # Make the API request to update the post
        # Add source=html query parameter to ensure proper HTML content handling
        response = await make_ghost_request(f"posts/{post_id}/?source=html", method="PUT", data=post_data)
        
        if "error" in response:
            return f"Error updating post: {response['error']}"
        
        # Extract relevant information from the response
        updated_post = response["posts"][0]
        return json.dumps({
            "id": updated_post["id"],
            "title": updated_post["title"],
            "url": updated_post["url"],
            "status": updated_post["status"],
            "updated_at": updated_post["updated_at"]
        }, indent=2)
    except (KeyError, IndexError) as e:
        return f"Error processing post data: {str(e)}"

if __name__ == "__main__":
    import sys
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport', type=str, default='sse', help='Transport type (stdio, sse, etc.)')
    args = parser.parse_args()
    mcp.run(transport=args.transport)

