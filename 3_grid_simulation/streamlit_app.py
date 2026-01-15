import streamlit as st
import simpy
import random
import pandas as pd
import statistics

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Utility Storm Response Twin", page_icon="⚡", layout="wide")

st.title("⚡ Utility Storm Response Digital Twin")
st.markdown("""
**Operational Simulation:** Adjust crew resources and storm severity to see the impact on 
**Mean Time to Restoration (MTTR)** and **Customer Wait Times**.
""")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("Simulation Parameters")
    
    num_crews = st.slider("Number of Repair Crews", min_value=1, max_value=50, value=5)
    storm_severity = st.slider("Storm Severity (Total Outages)", min_value=5, max_value=100, value=20)
    
    st.subheader("Operational Constraints")
    avg_travel = st.slider("Avg Travel Time (min)", 10, 120, 30)
    avg_repair = st.slider("Avg Repair Time (min)", 30, 240, 120)
    
    run_btn = st.button("Run Simulation", type="primary")

# --- SIMULATION ENGINE ---
class GridRestoration:
    def __init__(self, env, num_crews, travel_time, repair_time):
        self.env = env
        self.crews = simpy.Resource(env, capacity=num_crews)
        self.travel_time = travel_time
        self.repair_time = repair_time
        self.logs = []
        self.active_outages = 0
        self.outage_history = [] 

    def repair_outage(self, outage_id):
        arrival_time = self.env.now
        self.active_outages += 1
        self.outage_history.append({"time": self.env.now, "active": self.active_outages})

        with self.crews.request() as request:
            yield request
            wait_time = self.env.now - arrival_time
            
            # Simulate Travel & Repair
            travel = random.gauss(self.travel_time, 5) 
            yield self.env.timeout(travel)
            
            repair = random.expovariate(1.0 / self.repair_time)
            yield self.env.timeout(repair)
            
            self.active_outages -= 1
            self.outage_history.append({"time": self.env.now, "active": self.active_outages})
            
            self.logs.append({
                "Outage ID": outage_id,
                "Report Time": arrival_time,
                "Customer Wait (Min)": wait_time + travel + repair,
                "Crew Wait Time": wait_time,
                "Travel Time": travel,
                "Repair Time": repair
            })

def outage_generator(env, grid, severity):
    for i in range(severity):
        yield env.timeout(random.uniform(0, 600))
        env.process(grid.repair_outage(i))

# --- MAIN EXECUTION ---
if run_btn:
    env = simpy.Environment()
    grid = GridRestoration(env, num_crews, avg_travel, avg_repair)
    env.process(outage_generator(env, grid, storm_severity))
    with st.spinner('Simulating storm response logistics...'):
        env.run()
    
    if grid.logs:
        df = pd.DataFrame(grid.logs)
        col1, col2, col3 = st.columns(3)
        col1.metric("Avg Restoration Time (MTTR)", f"{df['Customer Wait (Min)'].mean():.0f} min")
        col2.metric("Longest Outage", f"{df['Customer Wait (Min)'].max():.0f} min")
        col3.metric("Crew Utilization", f"{(df['Repair Time'].sum() + df['Travel Time'].sum()) / (env.now * num_crews) * 100:.1f}%")
        
        st.subheader("Storm Recovery Curve")
        st.line_chart(pd.DataFrame(grid.outage_history).set_index("time"))
        
        st.subheader("Detailed Restoration Log")
        st.dataframe(df.sort_values("Report Time"), use_container_width=True)
    else:
        st.warning("No outages generated.")
else:
    st.info("Adjust parameters in the sidebar and click 'Run Simulation' to start.")