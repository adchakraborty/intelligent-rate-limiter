#!/usr/bin/env python3
"""
Test script for demo phase indicator functionality
"""
import asyncio
import aiohttp
import time

async def test_demo_phase():
    """Test the demo phase update endpoint"""
    base_url = "http://localhost:8080"
    
    async with aiohttp.ClientSession() as session:
        # Test phase updates
        phases = [
            (1, "ACT I: AI Learning"),
            (2, "ACT II: Launch Surge"), 
            (3, "ACT III: Peak Crisis"),
            (0, "Demo Complete")
        ]
        
        for phase, name in phases:
            print(f"🎬 Setting phase {phase}: {name}")
            
            # Update phase
            async with session.post(
                f"{base_url}/demo/phase",
                json={"phase": phase, "phase_name": name}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Phase updated: {data}")
                else:
                    print(f"❌ Failed to update phase: {response.status}")
            
            # Wait and check current phase
            await asyncio.sleep(2)
            
            async with session.get(f"{base_url}/demo/phase") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"📊 Current phase: {data['phase']} - {data.get('elapsed_seconds', 0):.1f}s elapsed")
                else:
                    print(f"❌ Failed to get phase: {response.status}")
            
            print()

if __name__ == "__main__":
    print("🧪 Testing FluxGuard AI Demo Phase Indicator...")
    print("Make sure the limiter service is running on localhost:8080")
    print()
    
    try:
        asyncio.run(test_demo_phase())
        print("✅ Demo phase test completed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")