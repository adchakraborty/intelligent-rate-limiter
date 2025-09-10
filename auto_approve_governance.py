#!/usr/bin/env python3
"""
🏆 Automatic Governance Approval for Hackathon Demo
Auto-approves pending decisions with Enterprise priority
"""

import asyncio
import aiohttp
import time
import signal
import sys
from typing import List, Dict

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    BOLD = '\033[1m'
    END = '\033[0m'

class AutoGovernanceApprover:
    def __init__(self, base_url="http://localhost:8080", check_interval=1.5):
        self.base_url = base_url
        self.check_interval = check_interval
        self.approval_delay = 2.0  # Wait 2 seconds before auto-approving
        self.running = True
        self.session = None
        self.stats = {
            "enterprise_approved": 0,
            "professional_approved": 0,
            "free_approved": 0,
            "total_checked": 0,
            "start_time": time.time()
        }
        
        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n{Colors.YELLOW}🛑 Stopping auto-approver...{Colors.END}")
        self.running = False
    
    async def start_session(self):
        """Initialize HTTP session"""
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    async def close_session(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
    
    async def get_pending_decisions(self) -> List[Dict]:
        """Get all pending governance decisions"""
        try:
            async with self.session.get(f"{self.base_url}/ai/pending") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("pending", [])
        except Exception as e:
            print(f"{Colors.RED}Error fetching pending decisions: {e}{Colors.END}")
        return []
    
    async def approve_decision(self, decision: Dict) -> bool:
        """Approve a specific decision"""
        try:
            decision_id = decision["id"]
            async with self.session.post(f"{self.base_url}/ai/approve/{decision_id}") as response:
                if response.status == 200:
                    tenant = decision.get("tenant", "unknown")
                    scaling_factor = decision.get("scaling_factor", 1.0)
                    
                    # Track by tier
                    if tenant == "ent":
                        self.stats["enterprise_approved"] += 1
                        tier_emoji = "🏆"
                        tier_color = Colors.GREEN
                    elif tenant == "pro":
                        self.stats["professional_approved"] += 1
                        tier_emoji = "💼"
                        tier_color = Colors.BLUE
                    else:
                        self.stats["free_approved"] += 1
                        tier_emoji = "🆓"
                        tier_color = Colors.YELLOW
                    
                    print(f"{tier_color}✅ {tier_emoji} APPROVED: {tenant.upper()} scaling {scaling_factor:.1f}x ({decision_id[:8]}...){Colors.END}")
                    return True
                    
        except Exception as e:
            print(f"{Colors.RED}Error approving decision: {e}{Colors.END}")
        return False
    
    async def process_pending_decisions(self):
        """Process pending decisions with delay to show governance effect"""
        pending = await self.get_pending_decisions()
        
        if not pending:
            return
        
        self.stats["total_checked"] += len(pending)
        current_time = time.time()
        
        # Sort by priority: Enterprise first, then Pro, then Free
        priority_order = {"ent": 0, "pro": 1, "free": 2}
        pending_sorted = sorted(pending, key=lambda d: priority_order.get(d.get("tenant", "free"), 3))
        
        approved_count = 0
        
        # Only approve decisions that have been pending for the delay period
        for decision in pending_sorted:
            decision_age = current_time - decision.get("created", current_time)
            scaling_factor = decision.get("scaling_factor", 1.0)
            tenant = decision.get("tenant", "unknown")
            
            # Only approve large changes (>2x) after the delay period
            if decision_age >= self.approval_delay and scaling_factor >= 2.0:
                await self.approve_decision(decision)
                approved_count += 1
            elif decision_age < self.approval_delay:
                remaining_delay = self.approval_delay - decision_age
                print(f"{Colors.YELLOW}⏳ {tenant.upper()} decision pending ({remaining_delay:.1f}s remaining){Colors.END}")
            elif scaling_factor < 2.0:
                print(f"{Colors.BLUE}ℹ️  {tenant.upper()} small change ({scaling_factor:.1f}x) - no approval needed{Colors.END}")
        
        if approved_count > 0:
            print(f"{Colors.BOLD}📋 Auto-approved {approved_count} decisions after delay{Colors.END}")
    
    def print_stats(self):
        """Print approval statistics"""
        elapsed = time.time() - self.stats["start_time"]
        total_approved = (self.stats["enterprise_approved"] + 
                         self.stats["professional_approved"] + 
                         self.stats["free_approved"])
        
        print(f"""
{Colors.BOLD}🏆 Auto-Approval Statistics:{Colors.END}
   {Colors.GREEN}🏆 Enterprise Approved: {self.stats['enterprise_approved']:,}{Colors.END}
   {Colors.BLUE}💼 Professional Approved: {self.stats['professional_approved']:,}{Colors.END}
   {Colors.YELLOW}🆓 Free Tier Approved: {self.stats['free_approved']:,}{Colors.END}
   {Colors.PURPLE}📊 Total Decisions Processed: {self.stats['total_checked']:,}{Colors.END}
   {Colors.CYAN}⚡ Total Approved: {total_approved:,}{Colors.END}
   {Colors.WHITE}⏱️  Runtime: {elapsed:.1f}s{Colors.END}
        """)
    
    async def run(self):
        """Main auto-approval loop"""
        print(f"{Colors.BOLD}{Colors.PURPLE}🏆 AUTO-GOVERNANCE APPROVER STARTED{Colors.END}")
        print(f"{Colors.PURPLE}{'=' * 50}{Colors.END}")
        print(f"{Colors.WHITE}🎯 Enterprise Priority: Auto-approve all{Colors.END}")
        print(f"{Colors.WHITE}💼 Professional: 90% auto-approval{Colors.END}")
        print(f"{Colors.WHITE}🆓 Free Tier: 60% auto-approval{Colors.END}")
        print(f"{Colors.WHITE}⏱️  Check interval: {self.check_interval}s{Colors.END}\n")
        
        await self.start_session()
        
        try:
            while self.running:
                await self.process_pending_decisions()
                self.print_stats()
                await asyncio.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}🛑 Interrupted by user{Colors.END}")
        finally:
            await self.close_session()
            print(f"{Colors.GREEN}👋 Auto-approver stopped{Colors.END}")

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="🏆 Auto-approve governance decisions")
    parser.add_argument("--url", default="http://localhost:8080", help="Rate limiter URL")
    parser.add_argument("--interval", type=float, default=1.5, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    approver = AutoGovernanceApprover(args.url, args.interval)
    
    # Health check first
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{args.url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    print(f"{Colors.RED}❌ Rate limiter not healthy (status: {response.status}){Colors.END}")
                    sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}❌ Cannot reach rate limiter: {e}{Colors.END}")
        sys.exit(1)
    
    await approver.run()

if __name__ == "__main__":
    asyncio.run(main())
