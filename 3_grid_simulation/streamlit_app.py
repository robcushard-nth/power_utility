import streamlit as st
import simpy
import random
import pandas as pd
import statistics
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Utility Risk Simulator (Monte Carlo)", page_icon="⚡", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ Utility Risk Simulator (Monte Carlo)")
st.markdown("""
**Risk Analysis:** Run thousands of "virtual storms" to determine the probability of failure.
""")

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("1. Monte Carlo Settings")
    iterations = st.slider("Simulation Runs", 10, 500, 100)
    
    st.divider()
    
    st.header("2. Resource Strategy")
    num_crews = st.slider("Repair Crews", 1, 50, 8)
    crew_rate = st.number_input("Crew Hourly Rate ($)", 350, step=50)
    
    st.header("3. Storm Profile")
    storm_severity = st.slider("Total Outages", 5, 200, 40)
    customers_per_outage = st.slider("Avg Customers/Outage", 10, 500, 125)
    total_customers = st.number_input("Total Grid Customers", 50000)

    st.header("4. Constraints")
    avg_travel = st.slider("Travel Time (min)", 10, 120, 30)
    avg_repair = st.slider("Repair Time (min)", 30, 240, 120)
    variability = st.slider("Uncertainty (Std Dev)", 1, 30, 15)
    
    run_btn = st.button("Run Monte Carlo Simulation", type="primary", use_container_width=True)

# --- SIMULATION ENGINE ---
class GridRestoration:
    def __init__(self, env, num_crews, travel, repair, var):
        self.env = env
        self.crews = simpy.Resource(env, capacity=num_crews)
        self.travel_base = travel
        self.repair_base = repair
        self.var = var
        self.logs = []

    def repair_outage(self, outage_id, cust_impact):
        arrival = self.env.now
        with self.crews.request() as req:
            yield req
            dispatch_wait = self.env.now - arrival
            
            # Stochastic Process
            travel = max(5, random.gauss(self.travel_base, self.var))
            repair = max(10, random.gauss(self.repair_base, self.var * 2))
            
            total_dur = dispatch_wait + travel + repair
            
            self.logs.append({
                "Outage ID": outage_id,
                "Customers": cust_impact,
                "Total Duration": total_dur,
                "Wait Time": dispatch_wait,
                "Cost": ((travel + repair)/60) * crew_rate
            })

def run_single_iteration(run_id):
    env = simpy.Environment()
    grid = GridRestoration(env, num_crews, avg_travel, avg_repair, variability)
    
    for i in range(storm_severity):
        env.process(grid.repair_outage(i, int(random.uniform(customers_per_outage*0.7, customers_per_outage*1.3))))
        
    env.run()
    
    if grid.logs:
        df = pd.DataFrame(grid.logs)
        df["Run ID"] = run_id
        return df
    return pd.DataFrame()

# --- MAIN EXECUTION ---
if run_btn:
    all_runs = []
    progress_bar = st.progress(0)
    
    # MONTE CARLO LOOP
    for i in range(iterations):
        run_df = run_single_iteration(i + 1)
        all_runs.append(run_df)
        progress_bar.progress((i + 1) / iterations)
    
    master_df = pd.concat(all_runs)
    
    # --- CALCULATE AGGREGATE METRICS PER RUN ---
    run_metrics = master_df.groupby("Run ID").apply(lambda x: pd.Series({
        "CAIDI": (x["Total Duration"] * x["Customers"]).sum() / x["Customers"].sum(),
        "SAIDI": (x["Total Duration"] * x["Customers"]).sum() / total_customers,
        "Total Cost": x["Cost"].sum(),
        "Max Wait": x["Total Duration"].max()
    }))

    # --- TABS LAYOUT ---
    tab1, tab2 = st.tabs(["📊 Executive Summary", "🎲 Risk & Probability Analysis"])

    # === TAB 1: AVERAGES ===
    with tab1:
        st.subheader(f"Expected Outcomes (Based on {iterations} Simulations)")
        
        # Means
        avg_caidi = run_metrics["CAIDI"].mean()
        avg_saidi = run_metrics["SAIDI"].mean()
        avg_cost = run_metrics["Total Cost"].mean()
        
        # 95th Percentile (Value at Risk)
        var_caidi = np.percentile(run_metrics["CAIDI"], 95)
        var_cost = np.percentile(run_metrics["Total Cost"], 95)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Avg CAIDI", f"{avg_caidi:.0f} min", f"95% Risk: {var_caidi:.0f} min", delta_color="inverse")
        col2.metric("Avg SAIDI", f"{avg_saidi:.2f} min")
        col3.metric("Avg Event Cost", f"${avg_cost:,.0f}", f"95% Risk: ${var_cost:,.0f}", delta_color="inverse")
        
        st.divider()
        
        # VISUAL 1: Cost vs Reliability Scatter
        st.markdown("#### Cost vs. Reliability Trade-off")
        st.markdown("Are we spending efficiently? Ideal scenario is **Bottom-Left** (Low Cost, Low CAIDI).")
        
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.scatterplot(data=run_metrics, x="Total Cost", y="CAIDI", alpha=0.6, color="blue", s=80, ax=ax)
        
        # Add Reference Lines (Averages)
        plt.axvline(avg_cost, color='red', linestyle='--', alpha=0.5, label='Avg Cost')
        plt.axhline(avg_caidi, color='red', linestyle='--', alpha=0.5, label='Avg CAIDI')
        plt.title("Each dot represents one full storm simulation")
        plt.legend()
        plt.grid(True, alpha=0.3)
        st.pyplot(fig)

    # === TAB 2: PROBABILITY & RISK ===
    with tab2:
        st.subheader("Probability of Failure")
        
        c1, c2 = st.columns(2)
        
        # VISUAL 2: Exceedance Probability (Inverse CDF)
        with c1:
            st.markdown("##### 📉 Likelihood of Delays (Exceedance Curve)")
            st.caption("What is the % chance that restoration takes longer than X minutes?")
            
            # Sort data
            sorted_caidi = np.sort(run_metrics["CAIDI"])
            # Calculate probability of exceeding (1 - CDF)
            y_vals = 1.0 - np.arange