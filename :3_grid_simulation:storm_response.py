import simpy
import random
import statistics

# --- CONFIGURATION ---
NUM_CREWS = 5              # Number of repair crews available
AVG_TRAVEL_TIME = 30       # Minutes to reach site
AVG_REPAIR_TIME = 120      # Minutes to fix a downed line
STORM_SEVERITY = 20        # Number of outages generated
SIMULATION_TIME = 1440     # Run for 24 hours (in minutes)

class GridRestoration:
    def __init__(self, env, num_crews):
        self.env = env
        self.crews = simpy.Resource(env, capacity=num_crews)
        self.wait_times = []

    def repair_outage(self, outage_id):
        """The lifecycle of a single repair job"""
        arrival_time = self.env.now
        
        # Request a crew (Resource Constraint)
        with self.crews.request() as request:
            yield request
            
            # Log: Crew dispatched
            response_time = self.env.now - arrival_time
            self.wait_times.append(response_time)
            # print(f"[{self.env.now:.1f}] 🚚 Crew dispatched to Outage #{outage_id} (Wait: {response_time} min)")
            
            # Simulate Travel Time (Stochastic)
            travel = random.gauss(AVG_TRAVEL_TIME, 5) 
            yield self.env.timeout(travel)
            
            # Simulate Repair Work (Stochastic)
            repair = random.expovariate(1.0 / AVG_REPAIR_TIME)
            yield self.env.timeout(repair)
            
            # print(f"[{self.env.now:.1f}] ✅ Outage #{outage_id} RESTORED.")

def outage_generator(env, grid):
    """Generates storm damage events over time"""
    for i in range(STORM_SEVERITY):
        yield env.timeout(random.uniform(10, 600)) 
        # print(f"[{env.now:.1f}] ⚡ REPORT: Outage #{i} detected!")
        env.process(grid.repair_outage(i))

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print(f"--- STARTING STORM SIMULATION (Crews: {NUM_CREWS}) ---")
    env = simpy.Environment()
    grid = GridRestoration(env, NUM_CREWS)
    env.process(outage_generator(env, grid))
    env.run(until=SIMULATION_TIME)

    # --- ANALYTICS ---
    avg_wait = statistics.mean(grid.wait_times) if grid.wait_times else 0
    print(f"\n--- RESULTS ---")
    print(f"Total Outages: {STORM_SEVERITY}")
    print(f"Average Customer Wait Time (CAIDI proxy): {avg_wait:.1f} minutes")
    print(f"Resource Utilization: {grid.crews.count} crews busy at end of shift")