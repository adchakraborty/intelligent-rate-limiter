#!/usr/bin/env python3
"""
🏆 Hackathon Load Generator for AI Rate Limiter Demo
Generates realistic traffic patterns to showcase AI vs Static performance
"""

import asyncio
import aiohttp
import random
import time
import json
import sys
from dataclasses import dataclass
from typing import List, Dict
import argparse
import signal

@dataclass
class LoadPattern:
    name: str
    duration: int  # seconds
    rps_ent: int
    rps_pro: int
    rps_free: int
    description: str
    surge_factor: float = 1.0

# 🎪 Hackathon demo scenarios (2-minute demo total)
SCENARIOS = {
    "startup": LoadPattern("🌅 Morning Startup", 20, 5, 3, 2, "Light morning traffic"),
    "business": LoadPattern("📈 Business Hours", 25, 15, 10, 5, "Normal operations"),
    "launch": LoadPattern("🚀 Product Launch", 30, 35, 25, 15, "Product announcement surge"),
    "blackfriday": LoadPattern("🛒 Black Friday", 25, 60, 40, 25, "Peak shopping event"),
    "ddos": LoadPattern("⚡ DDoS Attack", 20, 100, 80, 50, "Simulated attack", 2.0),
    "viral": LoadPattern("🔥 Viral Content", 25, 80, 60, 40, "Content going viral", 1.5),
    "maintenance": LoadPattern("🌙 Low Traffic", 10, 2, 1, 1, "Maintenance window"),
    "enterprise": LoadPattern("🏆 Enterprise Priority", 30, 50, 20, 8, "Enterprise gets priority scaling", 2.5),
}

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

class HackathonLoadGenerator:
    def __init__(self, base_url="http://localhost:8080", verbose=True):
        self.base_url = base_url
        self.verbose = verbose
        self.session = None
        self.running = True
        self.stats = {
            "requests_sent": 0,
            "responses_200": 0,
            "responses_429": 0,
            "responses_error": 0,
            "ai_decisions_seen": 0,
            "governance_events": 0,
            "auto_approvals": 0,
            "enterprise_prioritized": 0,
            "start_time": time.time()
        }
        
        # Auto-approval settings for governance demo
        self.auto_approve_enabled = True
        self.approval_interval = 2.0  # Check every 2 seconds
        self.approval_delay = 2.0     # Wait 2 seconds before auto-approving
        self.last_approval_check = 0
        
        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n{Colors.YELLOW}🛑 Stopping load generation...{Colors.END}")
        self.running = False
    
    async def start_session(self):
        """Initialize HTTP session"""
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    async def close_session(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
    
    async def send_request(self, tenant: str, endpoint: str = "/api/v1/resourceA"):
        """Send a single API request with proper authentication"""
        if not self.running:
            return 0
            
        api_keys = {
            "ent": "ent-key",
            "pro": "pro-key", 
            "free": "free-key"
        }
        
        headers = {
            "X-API-Key": api_keys[tenant],
            "Content-Type": "application/json",
            "User-Agent": f"HackathonDemo-{tenant.upper()}-{random.randint(1000,9999)}"
        }
        
        try:
            async with self.session.get(
                f"{self.base_url}{endpoint}",
                headers=headers
            ) as response:
                self.stats["requests_sent"] += 1
                
                status = response.status
                if status == 200:
                    self.stats["responses_200"] += 1
                elif status == 429:
                    self.stats["responses_429"] += 1
                else:
                    self.stats["responses_error"] += 1
                
                # Check for AI decision indicators
                if "X-AI-Decision" in response.headers:
                    self.stats["ai_decisions_seen"] += 1
                
                if "X-Governance-Required" in response.headers:
                    self.stats["governance_events"] += 1
                
                return status
                
        except asyncio.TimeoutError:
            self.stats["responses_error"] += 1
            return 408
        except Exception as e:
            if self.verbose:
                print(f"{Colors.RED}Request error: {e}{Colors.END}")
            self.stats["responses_error"] += 1
            return 500
    
    async def check_and_approve_decisions(self):
        """🏆 Auto-approve governance decisions after delay to show the effect"""
        if not self.auto_approve_enabled or not self.running:
            return
            
        try:
            # Get pending decisions
            async with self.session.get(f"{self.base_url}/ai/pending") as response:
                if response.status == 200:
                    data = await response.json()
                    pending = data.get("pending", [])
                    
                    if pending:
                        current_time = time.time()
                        
                        # Only auto-approve decisions that have been pending for the delay period
                        for decision in pending:
                            decision_age = current_time - decision.get("created", current_time)
                            scaling_factor = decision.get("scaling_factor", 1.0)
                            
                            # Only approve if it's been pending for the delay AND it's a large change (>2x)
                            if decision_age >= self.approval_delay and scaling_factor >= 2.0:
                                tenant = decision.get("tenant", "unknown")
                                reason = "🏆 ENT-AUTO" if tenant == "ent" else "AUTO-APPROVE"
                                
                                await self.approve_decision(decision["id"], reason)
                                
                                if tenant == "ent":
                                    self.stats["enterprise_prioritized"] += 1
                                    
                                if self.verbose:
                                    print(f"{Colors.CYAN}⏰ Auto-approved {scaling_factor:.1f}x scaling for {tenant} after {decision_age:.1f}s delay{Colors.END}")
                            
        except Exception as e:
            if self.verbose:
                print(f"{Colors.YELLOW}Auto-approval error: {e}{Colors.END}")
    
    async def approve_decision(self, decision_id: str, reason: str = "AUTO"):
        """Approve a specific governance decision"""
        try:
            async with self.session.post(f"{self.base_url}/ai/approve/{decision_id}") as response:
                if response.status == 200:
                    self.stats["auto_approvals"] += 1
                    if self.verbose:
                        print(f"{Colors.GREEN}✅ {reason}: Approved decision {decision_id[:8]}...{Colors.END}")
                    return True
        except Exception as e:
            if self.verbose:
                print(f"{Colors.RED}Approval error for {decision_id}: {e}{Colors.END}")
        return False
    
    async def run_pattern(self, pattern: LoadPattern, show_progress=True):
        """Execute a specific load pattern"""
        if show_progress:
            print(f"\n{Colors.BOLD}{Colors.CYAN}{pattern.name}{Colors.END}")
            print(f"{Colors.WHITE}📝 {pattern.description}{Colors.END}")
            print(f"{Colors.WHITE}⏱️  Duration: {pattern.duration}s{Colors.END}")
            print(f"{Colors.WHITE}🎛️  Target RPS: Ent={pattern.rps_ent}, Pro={pattern.rps_pro}, Free={pattern.rps_free}{Colors.END}")
        
        start_time = time.time()
        tasks = []
        
        # Calculate intervals between requests
        intervals = {
            "ent": 1.0 / pattern.rps_ent if pattern.rps_ent > 0 else float('inf'),
            "pro": 1.0 / pattern.rps_pro if pattern.rps_pro > 0 else float('inf'),
            "free": 1.0 / pattern.rps_free if pattern.rps_free > 0 else float('inf')
        }
        
        async def request_scheduler(tenant: str, interval: float):
            """Schedule requests for a specific tenant at target RPS"""
            next_request_time = time.time()
            requests_sent = 0
            
            while self.running and (time.time() - start_time) < pattern.duration:
                current_time = time.time()
                
                # 🏆 Periodic auto-approval check to keep governance flowing
                if current_time - self.last_approval_check > self.approval_interval:
                    await self.check_and_approve_decisions()
                    self.last_approval_check = current_time
                
                if current_time >= next_request_time:
                    # ALWAYS send requests to ensure AI threshold is met
                    # Add surge factor for dramatic effect
                    surge_multiplier = 1.0
                    if pattern.surge_factor > 1.0:
                        # Gradual surge build-up
                        progress = (current_time - start_time) / pattern.duration
                        surge_multiplier = 1.0 + (pattern.surge_factor - 1.0) * progress
                    
                    # Send base request ALWAYS (ensures AI threshold met)
                    task = asyncio.create_task(self.send_request(tenant))
                    tasks.append(task)
                    requests_sent += 1
                    
                    # Send additional requests based on surge factor
                    if surge_multiplier > 1.1 and random.random() < (surge_multiplier - 1.0):
                        extra_task = asyncio.create_task(self.send_request(tenant))
                        tasks.append(extra_task)
                        requests_sent += 1
                    
                    next_request_time += interval
                
                # Small sleep to prevent busy waiting
                await asyncio.sleep(max(0.01, min(0.1, interval / 10)))
            
            return requests_sent
        
        # Start request schedulers for each tenant tier
        schedulers = []
        for tenant, interval in intervals.items():
            if interval != float('inf'):
                schedulers.append(request_scheduler(tenant, interval))
        
        # Run all schedulers concurrently
        if schedulers:
            scheduler_results = await asyncio.gather(*schedulers, return_exceptions=True)
        
        # Wait for any pending requests to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        if show_progress:
            print(f"{Colors.GREEN}✅ Completed: {pattern.name} ({elapsed:.1f}s){Colors.END}")
            self.print_stats()
    
    def print_stats(self):
        """Print current performance statistics"""
        elapsed = time.time() - self.stats["start_time"]
        rps = self.stats["requests_sent"] / max(elapsed, 1)
        
        success_rate = 0
        if self.stats["requests_sent"] > 0:
            success_rate = (self.stats["responses_200"] / self.stats["requests_sent"]) * 100
        
        print(f"""
{Colors.BOLD}📊 Performance Metrics:{Colors.END}
   {Colors.GREEN}📤 Total Requests: {self.stats['requests_sent']:,}{Colors.END}
   {Colors.GREEN}✅ Success (200): {self.stats['responses_200']:,}{Colors.END}
   {Colors.YELLOW}🚫 Rate Limited (429): {self.stats['responses_429']:,}{Colors.END}
   {Colors.RED}❌ Errors: {self.stats['responses_error']:,}{Colors.END}
   {Colors.BLUE}🤖 AI Decisions: {self.stats['ai_decisions_seen']:,}{Colors.END}
   {Colors.PURPLE}⚖️ Governance Events: {self.stats['governance_events']:,}{Colors.END}
   {Colors.BOLD}{Colors.GREEN}🏆 Auto-Approvals: {self.stats['auto_approvals']:,}{Colors.END}
   {Colors.BOLD}{Colors.PURPLE}👑 Enterprise Priority: {self.stats['enterprise_prioritized']:,}{Colors.END}
   {Colors.CYAN}⚡ Average RPS: {rps:.1f}{Colors.END}
   {Colors.WHITE}📈 Success Rate: {success_rate:.1f}%{Colors.END}
        """)
    
    async def run_scenario(self, scenario_name: str):
        """Run a single named scenario"""
        if scenario_name not in SCENARIOS:
            print(f"{Colors.RED}❌ Unknown scenario: {scenario_name}{Colors.END}")
            print(f"{Colors.WHITE}Available scenarios: {', '.join(SCENARIOS.keys())}{Colors.END}")
            return
        
        await self.start_session()
        try:
            await self.run_pattern(SCENARIOS[scenario_name])
        finally:
            await self.close_session()
    
    async def run_hackathon_demo(self):
        """Run the complete hackathon demonstration sequence"""
        print(f"{Colors.BOLD}{Colors.PURPLE}🏆 HACKATHON AI RATE LIMITER DEMO{Colors.END}")
        print(f"{Colors.PURPLE}{'=' * 60}{Colors.END}")
        print(f"{Colors.WHITE}🎯 Showcasing AI vs Static Rate Limiting{Colors.END}")
        print(f"{Colors.WHITE}🚀 Real traffic → AI decisions → Revenue protection{Colors.END}\n")
        
        await self.start_session()
        
        try:
            # Demo sequence designed for maximum impact (2-minute total)
            demo_sequence = [
                ("business", "Normal business operations"), 
                ("launch", "Product launch surge with AI scaling"),
                ("blackfriday", "Peak traffic - AI governance in action!")
            ]
            
            for i, (scenario_name, description) in enumerate(demo_sequence, 1):
                if not self.running:
                    break
                    
                print(f"\n{Colors.BOLD}{Colors.BLUE}🎬 Phase {i}/{len(demo_sequence)}: {description}{Colors.END}")
                await self.run_pattern(SCENARIOS[scenario_name])
                
                # Short cool-down between phases (except last one)
                if i < len(demo_sequence) and self.running:
                    print(f"{Colors.YELLOW}⏸️  Cooling down for 2 seconds...{Colors.END}")
                    await asyncio.sleep(2)
            
            if self.running:
                print(f"\n{Colors.BOLD}{Colors.GREEN}🏁 HACKATHON DEMO COMPLETE!{Colors.END}")
                print(f"{Colors.GREEN}🎯 Check Grafana dashboard for AI vs Static comparison{Colors.END}")
                print(f"{Colors.GREEN}📊 Dashboard: http://localhost:3000{Colors.END}")
            
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}🛑 Demo interrupted by user{Colors.END}")
        finally:
            await self.close_session()
    
    async def health_check(self):
        """Check if the rate limiter is responding"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        print(f"{Colors.GREEN}✅ Rate limiter is healthy{Colors.END}")
                        return True
                    else:
                        print(f"{Colors.RED}❌ Rate limiter returned status {response.status}{Colors.END}")
                        return False
        except Exception as e:
            print(f"{Colors.RED}❌ Cannot reach rate limiter: {e}{Colors.END}")
            return False

async def main():
    parser = argparse.ArgumentParser(description="🏆 Hackathon AI Rate Limiter Load Generator")
    parser.add_argument("--url", default="http://localhost:8080", help="Rate limiter URL")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), help="Run specific scenario")
    parser.add_argument("--demo", action="store_true", help="Run full hackathon demo")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    parser.add_argument("--check", action="store_true", help="Health check only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.list:
        print(f"{Colors.BOLD}📋 Available Scenarios:{Colors.END}")
        for name, pattern in SCENARIOS.items():
            print(f"  {Colors.CYAN}{name:12}{Colors.END} - {pattern.description}")
        return
    
    generator = HackathonLoadGenerator(args.url, args.verbose)
    
    if args.check:
        await generator.health_check()
        return
    
    # Health check first
    if not await generator.health_check():
        print(f"{Colors.RED}🚨 Cannot proceed - rate limiter is not accessible{Colors.END}")
        sys.exit(1)
    
    if args.demo:
        await generator.run_hackathon_demo()
    elif args.scenario:
        await generator.run_scenario(args.scenario)
    else:
        # Interactive mode
        print(f"{Colors.BOLD}🎯 Interactive Mode{Colors.END}")
        print(f"{Colors.WHITE}Available commands:{Colors.END}")
        print(f"  {Colors.CYAN}demo{Colors.END}     - Run full hackathon demo")
        print(f"  {Colors.CYAN}<scenario>{Colors.END} - Run specific scenario")
        print(f"  {Colors.CYAN}list{Colors.END}     - Show available scenarios")
        print(f"  {Colors.CYAN}quit{Colors.END}     - Exit")
        
        while True:
            try:
                cmd = input(f"\n{Colors.BOLD}> {Colors.END}").strip().lower()
                if cmd in ["quit", "exit", "q"]:
                    break
                elif cmd == "demo":
                    await generator.run_hackathon_demo()
                elif cmd == "list":
                    for name, pattern in SCENARIOS.items():
                        print(f"  {Colors.CYAN}{name:12}{Colors.END} - {pattern.description}")
                elif cmd in SCENARIOS:
                    await generator.run_scenario(cmd)
                else:
                    print(f"{Colors.RED}❌ Unknown command: {cmd}{Colors.END}")
            except (KeyboardInterrupt, EOFError):
                break
        
        print(f"{Colors.GREEN}👋 Goodbye!{Colors.END}")

if __name__ == "__main__":
    asyncio.run(main())
