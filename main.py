import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

# Configuration
GOOGLE_API_KEY = ""
if not GOOGLE_API_KEY:
    raise ValueError("❌ GOOGLE_API_KEY environment variable is required")

# Initialize the Modern Client
client = genai.Client(api_key=GOOGLE_API_KEY)

# System prompt for the agent
SYSTEM_PROMPT = """You are an agent responsible for resolving inconsistencies in customer return invoices.
Your goal is to find the company's original outbound invoice based on the information from the customer's return invoice.

**Return Invoice Data (Mandatory Input)**
- `customer`  
- `description`  
- `price`  
- `location`  

### Tasks
1. Search for outbound invoices using `search_invoices_by_criteria`.
2. Generate candidate EANs by combining results from `search_vectorized_product` and `resolve_ean`.
3. Check if EANs match any invoices found.
4. Display List "C" (Matched Invoices).
"""

# Tool definitions using the modern SDK style
# We pass these as a list of tools to the model
TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_vectorized_product",
                description="Searches for a product by description using semantic embeddings. Returns similar products with codes and descriptions.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "description": types.Schema(type="STRING", description="The product description to search for")
                    },
                    required=["description"]
                )
            ),
            types.FunctionDeclaration(
                name="resolve_ean",
                description="Resolves the product's EAN code based on its description using advanced search techniques.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "description": types.Schema(type="STRING", description="The product description to resolve an EAN for")
                    },
                    required=["description"]
                )
            ),
            types.FunctionDeclaration(
                name="search_invoices_by_criteria",
                description="Searches for A/R invoices based on customer, state, EAN, and/or price.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "customer": types.Schema(type="STRING", description="Customer name"),
                        "state": types.Schema(type="STRING", description="State code (e.g., SP, RJ)"),
                        "ean": types.Schema(type="STRING", description="Product EAN code"),
                        "price": types.Schema(type="NUMBER", description="Product price"),
                        "margin": types.Schema(type="NUMBER", description="Price margin (default: 0.05)")
                    }
                )
            )
        ]
    )
]

class MemoryState:
    """Conversation history for the modern SDK"""
    def __init__(self):
        self.history = []

    def add_user_message(self, content):
        self.history.append(types.Content(role="user", parts=[types.Part(text=content)]))

    def add_assistant_message(self, parts):
        self.history.append(types.Content(role="model", parts=parts))

    def add_tool_result(self, call_id, tool_name, result):
        """Add tool execution result to history"""
        self.history.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={"result": result}
                        )
                    )
                ]
            )
        )

async def call_mcp_tool(mcp_session: ClientSession, tool_name: str, tool_input: dict) -> dict:
    """Call a tool through the MCP server"""
    try:
        result = await mcp_session.call_tool(tool_name, tool_input)
        # Assuming MCP server returns text/json in the first content block
        return result.content[0].text if result.content else {}
    except Exception as e:
        return {"error": str(e)}

async def run_agent_loop(mcp_session: ClientSession, query: str, memory_state: MemoryState):
    """Modern ReAct Agent Loop"""
    memory_state.add_user_message(query)
    
    print("\n🤖 Agent Processing...")
    
    while True:
        try:
            # Generate content using history and tools
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=TOOLS,
                    temperature=0.1
                ),
                contents=memory_state.history
            )
        except Exception as e:
            print(f"❌ Error calling Gemini: {e}")
            break

        if not response.candidates:
            break

        candidate = response.candidates[0]
        # Store model's turn in history
        memory_state.add_assistant_message(candidate.content.parts)

        # Check for function calls
        function_calls = [p.function_call for p in candidate.content.parts if p.function_call]

        if not function_calls:
            # Final text response
            for part in candidate.content.parts:
                if part.text:
                    print(f"\n✅ Assistant: {part.text}")
            break

        # Process function calls
        for fc in function_calls:
            print(f"🔧 Tool: {fc.name} | Args: {fc.args}")
            
            # Execute via MCP
            result = await call_mcp_tool(mcp_session, fc.name, fc.args)
            
            # Feed back to history
            memory_state.add_tool_result(None, fc.name, result)

async def main():
    print("🚀 Connecting to MCP server...")
    
    server_params = StdioServerParameters(
        command="python",
        args=["server_invoice_items.py"]
    )
    
    try:
        async with stdio_client(server_params) as mcp_transport:
            mcp_session, _ = mcp_transport
            await mcp_session.initialize()
            print("✅ MCP Server connected")
            
            memory_state = MemoryState()
            
            print("\n" + "="*60)
            print("🎯 Invoice Resolution Agent (v2.0)")
            print("="*60)
            
            while True:
                try:
                    query = input("You: ").strip()
                    if query.lower() in ["quit", "exit"]: break
                    if not query: continue
                    
                    await run_agent_loop(mcp_session, query, memory_state)
                    
                except KeyboardInterrupt: break
                except Exception as e:
                    print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())