#!/usr/bin/env python3
"""
🏆 Enterprise Priority Demo Script
Demonstrates how enterprise customers get priority treatment
"""

import asyncio
import subprocess
import sys
import time
import signal

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

class EnterprisePriorityDemo:
    def __init__(self):
        self.processes = []
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n{Colors.YELLOW}🛑 Stopping enterprise demo...{Colors.END}")
        self.running = False
        self.cleanup()
    
    def cleanup(self):
        """Stop all child processes"""
        for proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass
    
    def start_background_process(self, command, name):
        """Start a background process"""
        try:
            proc = subprocess.Popen(command, shell=True)
            self.processes.append(proc)
            print(f"{Colors.GREEN}✅ Started {name}{Colors.END}")
            return proc
        except Exception as e:
            print(f"{Colors.RED}❌ Failed to start {name}: {e}{Colors.END}")
            return None
    
    def run_demo(self):
        """Run the enterprise priority demonstration"""
        print(f"{Colors.BOLD}{Colors.PURPLE}🏆 ENTERPRISE PRIORITY DEMONSTRATION{Colors.END}")
        print(f"{Colors.PURPLE}{'=' * 60}{Colors.END}")
        print(f"{Colors.WHITE}This demo shows how AI rate limiting gives enterprise customers priority{Colors.END}")
        print(f"{Colors.WHITE}during high-traffic scenarios while maintaining fairness for all tiers.{Colors.END}")
        print()
        
        # Phase 1: Start auto-approver
        print(f"{Colors.BOLD}{Colors.CYAN}Phase 1: Starting Auto-Governance Approver{Colors.END}")
        print(f"{Colors.WHITE}🤖 This simulates automated decision-making with enterprise priority{Colors.END}")
        
        approver_proc = self.start_background_process(
            "python auto_approve_governance.py --interval 1.0",
            "Auto-Governance Approver"
        )
        
        if not approver_proc:
            print(f"{Colors.RED}❌ Failed to start auto-approver. Exiting.{Colors.END}")
            return
        
        time.sleep(3)
        
        # Phase 2: Start load generation
        print(f"\n{Colors.BOLD}{Colors.CYAN}Phase 2: Enterprise Priority Load Test{Colors.END}")
        print(f"{Colors.WHITE}🏆 Watch enterprise customers scale seamlessly during traffic surges{Colors.END}")
        print(f"{Colors.WHITE}📊 Monitor the Grafana dashboard: http://localhost:3000{Colors.END}")
        print()
        
        demo_scenarios = [
            ("business", "📈 Normal operations"),
            ("launch", "🚀 Product launch surge"),
            ("blackfriday", "🛒 Peak traffic with governance")
        ]
        
        for scenario, description in demo_scenarios:
            if not self.running:
                break
                
            print(f"{Colors.BOLD}{Colors.BLUE}🎬 Running: {description}{Colors.END}")
            
            try:
                result = subprocess.run(
                    f"python load_generator.py --scenario {scenario}",
                    shell=True,
                    timeout=120,
                    capture_output=False
                )
                
                if result.returncode != 0:
                    print(f"{Colors.YELLOW}⚠️  Scenario completed with warnings{Colors.END}")
                    
            except subprocess.TimeoutExpired:
                print(f"{Colors.YELLOW}⏰ Scenario timed out (continuing){Colors.END}")
            except KeyboardInterrupt:
                print(f"{Colors.YELLOW}🛑 Demo interrupted{Colors.END}")
                break
            except Exception as e:
                print(f"{Colors.RED}❌ Scenario error: {e}{Colors.END}")
            
            if self.running:
                print(f"{Colors.CYAN}⏸️  Cooldown (2 seconds)...{Colors.END}")
                time.sleep(2)
        
        # Demo completed
        if self.running:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🏁 ENTERPRISE PRIORITY DEMO COMPLETE!{Colors.END}")
            print(f"{Colors.GREEN}{'=' * 50}{Colors.END}")
            print(f"{Colors.WHITE}Key observations from the dashboard:{Colors.END}")
            print(f"{Colors.GREEN}✅ Enterprise customers received priority scaling{Colors.END}")
            print(f"{Colors.GREEN}✅ AI decisions were auto-approved for enterprise tier{Colors.END}")
            print(f"{Colors.GREEN}✅ Revenue protection maximized during surges{Colors.END}")
            print(f"{Colors.GREEN}✅ System maintained fairness across all tiers{Colors.END}")
            print()
            print(f"{Colors.CYAN}📊 Check the Grafana dashboard for detailed metrics:{Colors.END}")
            print(f"{Colors.WHITE}   • Enterprise Scaling Advantage panel shows tier differences{Colors.END}")
            print(f"{Colors.WHITE}   • Revenue Protection shows enterprise value preserved{Colors.END}")
            print(f"{Colors.WHITE}   • AI Decision Stream shows auto-approval patterns{Colors.END}")
            print()
            print(f"{Colors.PURPLE}🎯 This demonstrates the business value of AI-powered rate limiting{Colors.END}")
            print(f"{Colors.PURPLE}   with intelligent governance and customer tier prioritization!{Colors.END}")
        
        # Keep auto-approver running for a bit longer
        if approver_proc and approver_proc.poll() is None:
            print(f"\n{Colors.YELLOW}⏳ Keeping auto-approver running for 10 more seconds...{Colors.END}")
            print(f"{Colors.WHITE}   (Press Ctrl+C to stop early){Colors.END}")
            
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                print(f"{Colors.YELLOW}🛑 Stopped by user{Colors.END}")
        
        self.cleanup()
        print(f"{Colors.GREEN}👋 Enterprise priority demo finished!{Colors.END}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="🏆 Enterprise Priority Demo")
    parser.add_argument("--quick", action="store_true", help="Quick demo (shorter scenarios)")
    
    args = parser.parse_args()
    
    # Check if required files exist
    import os
    required_files = ["load_generator.py", "auto_approve_governance.py"]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"{Colors.RED}❌ Missing required files: {', '.join(missing_files)}{Colors.END}")
        sys.exit(1)
    
    demo = EnterprisePriorityDemo()
    
    try:
        demo.run_demo()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}🛑 Demo interrupted by user{Colors.END}")
        demo.cleanup()
    except Exception as e:
        print(f"{Colors.RED}❌ Demo error: {e}{Colors.END}")
        demo.cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()
