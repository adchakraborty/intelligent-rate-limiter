#!/usr/bin/env python3
"""
🏆 HACKATHON AI RATE LIMITER - Ultimate Demo Runner
Complete demo script for 2.5 minute presentation
"""

import asyncio
import aiohttp
import time
import sys
import json
from datetime import datetime

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

class HackathonDemo:
    def __init__(self):
        self.base_url = "http://localhost:8080"
        self.session = None
        
    async def start_session(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    def print_banner(self, text, color=Colors.CYAN):
        print(f"\n{color}{Colors.BOLD}{'=' * 60}{Colors.END}")
        print(f"{color}{Colors.BOLD}{text.center(60)}{Colors.END}")
        print(f"{color}{Colors.BOLD}{'=' * 60}{Colors.END}\n")
    
    def print_step(self, step, description, color=Colors.WHITE):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{Colors.BLUE}[{timestamp}]{Colors.END} {color}{step}{Colors.END} {description}")
    
    async def check_health(self):
        """Check if all services are running"""
        services = {
            "AI Rate Limiter": f"{self.base_url}/health",
            "Grafana": "http://localhost:3000",
            "Prometheus": "http://localhost:9090/-/ready"
        }
        
        self.print_step("🔍", "Checking service health...")
        
        all_healthy = True
        for name, url in services.items():
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        print(f"   ✅ {name}: Healthy")
                    else:
                        print(f"   ⚠️  {name}: Status {response.status}")
                        all_healthy = False
            except Exception as e:
                print(f"   ❌ {name}: Failed - {e}")
                all_healthy = False
        
        return all_healthy
    
    async def reset_demo(self):
        """Reset demo to clean state"""
        self.print_step("🔄", "Resetting demo to baseline state...")
        
        try:
            async with self.session.post(f"{self.base_url}/api/demo/reset") as response:
                if response.status == 200:
                    print("   ✅ Demo reset successful")
                    return True
        except Exception as e:
            print(f"   ❌ Reset failed: {e}")
        return False
    
    async def get_metrics_snapshot(self):
        """Get current metrics for display"""
        try:
            async with self.session.get(f"{self.base_url}/demo/metrics") as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            print(f"   ⚠️  Metrics fetch failed: {e}")
        return {}
    
    def display_metrics(self, metrics, title="Current Metrics"):
        """Display metrics in a nice format"""
        print(f"\n{Colors.YELLOW}{Colors.BOLD}{title}:{Colors.END}")
        
        if "tiers" in metrics:
            for tier, data in metrics["tiers"].items():
                rps = data.get("effective_rps", 0)
                limit = data.get("rps_limit", 0)
                blocked = data.get("blocked_ratio", 0) * 100
                
                print(f"   {Colors.CYAN}{tier.upper():5}{Colors.END}: "
                      f"{rps:6.1f} RPS / {limit:4.1f} limit "
                      f"({Colors.RED if blocked > 10 else Colors.GREEN}{blocked:4.1f}% blocked{Colors.END})")
        
        if "governance" in metrics:
            pending = metrics["governance"].get("pending_count", 0)
            if pending > 0:
                print(f"   {Colors.PURPLE}GOVERNANCE{Colors.END}: {pending} decisions pending")
    
    async def simulate_traffic(self, tenant, requests=50):
        """Simulate traffic for a specific tenant"""
        try:
            payload = {"tenant": tenant, "requests": requests}
            async with self.session.post(f"{self.base_url}/debug/simulate-traffic", json=payload) as response:
                if response.status == 200:
                    return True
        except Exception as e:
            print(f"   ⚠️  Traffic simulation failed: {e}")
        return False
    
    async def trigger_demo_phase(self, phase):
        """Trigger a specific demo phase"""
        try:
            async with self.session.post(f"{self.base_url}/api/demo/trigger/{phase}") as response:
                if response.status == 200:
                    result = await response.json()
                    return result
        except Exception as e:
            print(f"   ⚠️  Phase trigger failed: {e}")
        return {}
    
    async def run_complete_demo(self):
        """Run the complete 2.5 minute hackathon demo"""
        
        await self.start_session()
        
        try:
            self.print_banner("🏆 HACKATHON AI RATE LIMITER DEMO", Colors.PURPLE)
            
            # 1. Health Check (10 seconds)
            self.print_step("1️⃣", "System Health Check", Colors.GREEN)
            if not await self.check_health():
                print(f"{Colors.RED}❌ Some services are not healthy. Please run setup first.{Colors.END}")
                return False
            
            # 2. Reset and Baseline (10 seconds)
            self.print_step("2️⃣", "Establishing Baseline", Colors.BLUE)
            await self.reset_demo()
            baseline_metrics = await self.get_metrics_snapshot()
            self.display_metrics(baseline_metrics, "Baseline State")
            await asyncio.sleep(3)
            
            # 3. Normal Traffic (20 seconds)
            self.print_step("3️⃣", "Simulating Normal Business Traffic", Colors.CYAN)
            await self.simulate_traffic("pro", 30)
            await self.simulate_traffic("ent", 20)
            await asyncio.sleep(5)
            
            normal_metrics = await self.get_metrics_snapshot()
            self.display_metrics(normal_metrics, "Normal Traffic")
            await asyncio.sleep(5)
            
            # 4. Surge Event (30 seconds)
            self.print_step("4️⃣", "🚀 Product Launch Surge!", Colors.YELLOW)
            print(f"   {Colors.WHITE}Simulating viral product announcement...{Colors.END}")
            
            await self.trigger_demo_phase(3)  # Launch phase
            await asyncio.sleep(8)
            
            surge_metrics = await self.get_metrics_snapshot()
            self.display_metrics(surge_metrics, "Surge Event - AI Adapting!")
            await asyncio.sleep(10)
            
            # 5. Black Friday Peak (40 seconds)
            self.print_step("5️⃣", "🛒 Black Friday Peak Traffic!", Colors.RED)
            print(f"   {Colors.WHITE}Maximum load - AI vs Static comparison{Colors.END}")
            
            await self.trigger_demo_phase(4)  # Peak phase
            await asyncio.sleep(12)
            
            peak_metrics = await self.get_metrics_snapshot()
            self.display_metrics(peak_metrics, "Peak Load - AI Optimization")
            
            # 6. AI Governance Demo (20 seconds)
            if peak_metrics.get("governance", {}).get("pending_count", 0) > 0:
                self.print_step("6️⃣", "⚖️ AI Governance in Action", Colors.PURPLE)
                print(f"   {Colors.WHITE}Large policy changes require human approval{Colors.END}")
                await asyncio.sleep(8)
            
            # 7. Results Summary (15 seconds)
            self.print_step("7️⃣", "📊 Demo Results Summary", Colors.GREEN)
            
            final_metrics = await self.get_metrics_snapshot()
            self.display_metrics(final_metrics, "Final State")
            
            # Summary stats
            print(f"\n{Colors.BOLD}{Colors.GREEN}🏆 DEMO COMPLETE - KEY ACHIEVEMENTS:{Colors.END}")
            print(f"{Colors.WHITE}  ✅ AI-powered intelligent rate limiting{Colors.END}")
            print(f"{Colors.WHITE}  ✅ Revenue-aware business optimization{Colors.END}")
            print(f"{Colors.WHITE}  ✅ Real-time adaptive scaling{Colors.END}")
            print(f"{Colors.WHITE}  ✅ Governance for large policy changes{Colors.END}")
            print(f"{Colors.WHITE}  ✅ Superior performance vs static limits{Colors.END}")
            
            # URLs for judges
            print(f"\n{Colors.CYAN}{Colors.BOLD}🎯 FOR JUDGES TO EXPLORE:{Colors.END}")
            print(f"{Colors.WHITE}  📊 Live Dashboard: http://localhost:3000{Colors.END}")
            print(f"{Colors.WHITE}  🔍 Metrics API:    http://localhost:8080/demo/metrics{Colors.END}")
            print(f"{Colors.WHITE}  ⚡ Load Generator: python load_generator.py --demo{Colors.END}")
            
            return True
            
        finally:
            await self.close_session()
    
    async def run_quick_demo(self):
        """Quick 30-second demo for time constraints"""
        await self.start_session()
        
        try:
            self.print_banner("⚡ QUICK AI RATE LIMITER DEMO", Colors.YELLOW)
            
            self.print_step("⚡", "Quick System Check", Colors.GREEN)
            await self.check_health()
            
            self.print_step("⚡", "AI Traffic Adaptation", Colors.CYAN)
            await self.simulate_traffic("ent", 100)
            await asyncio.sleep(5)
            
            metrics = await self.get_metrics_snapshot()
            self.display_metrics(metrics, "AI Adaptation Results")
            
            print(f"\n{Colors.GREEN}🚀 AI Rate Limiter: Intelligent, Revenue-Aware, Adaptive!{Colors.END}")
            print(f"{Colors.CYAN}Full demo: python hackathon_demo.py{Colors.END}")
            
        finally:
            await self.close_session()


async def main():
    demo = HackathonDemo()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--quick":
            print("Running 30-second quick demo...")
            await demo.run_quick_demo()
        elif sys.argv[1] == "--help":
            print("Hackathon AI Rate Limiter Demo")
            print("Usage:")
            print("  python hackathon_demo.py        - Full 2.5 minute demo")
            print("  python hackathon_demo.py --quick - 30 second demo")
            print("  python hackathon_demo.py --help  - This help")
            return
    else:
        print("Running complete 2.5 minute hackathon demo...")
        success = await demo.run_complete_demo()
        if not success:
            print(f"\n{Colors.RED}Demo failed. Please check service health.{Colors.END}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
