# ==================================================================================================
# UTILITY SPECIFICATION: Helpers
# ==================================================================================================
#
# PURPOSE:
#   - To store reusable, business-logic functions that can be imported and used across multiple views.
#   - This promotes the DRY (Don't Repeat Yourself) principle and keeps the view files focused on
#     UI rendering and workflow, separating complex calculations into a dedicated module.
#
# CONTAINED FUNCTIONS:
#   - calculate_oee: A function dedicated to calculating Overall Equipment Effectiveness.
#
# --------------------------------------------------------------------------------------------------
# FUNCTION: calculate_oee(df_prod)
# --------------------------------------------------------------------------------------------------
#   - DESCRIPTION:
#     - Takes a Pandas DataFrame containing production data and computes the OEE score along
#       with its three constituent components: Availability, Performance, and Quality.
#
#   - PARAMETERS:
#     - df_prod (pd.DataFrame): A DataFrame that must contain the following columns:
#       - PLANNED_RUNTIME_HOURS (float/int): Total time the asset was scheduled to run.
#       - ACTUAL_RUNTIME_HOURS (float/int): Total time the asset was actually running.
#       - UNITS_PRODUCED (int): Total number of units produced, including defects.
#       - UNITS_SCRAPPED (int): Number of units that were rejected for quality reasons.
#
#   - RETURNS:
#     - tuple: A tuple containing four float values in the following order:
#       1. oee (float): The final OEE score (Availability * Performance * Quality).
#       2. availability (float): The ratio of actual runtime to planned runtime.
#       3. performance (float): The ratio of actual output to potential output during runtime.
#       4. quality (float): The ratio of good units to total units produced.
#
#   - CALCULATION LOGIC:
#     - Availability = SUM(ACTUAL_RUNTIME_HOURS) / SUM(PLANNED_RUNTIME_HOURS)
#     - Quality = (SUM(UNITS_PRODUCED) - SUM(UNITS_SCRAPPED)) / SUM(UNITS_PRODUCED)
#     - Performance: For this dashboard, Performance is a simplified, fixed value (95%). In a
#       production environment, this would be a dynamic calculation based on ideal cycle times.
#
# ==================================================================================================

import pandas as pd

def calculate_oee(df_prod: pd.DataFrame) -> tuple[float, float, float, float]:
    """
    Calculates OEE from a production log dataframe.
    OEE = Availability * Performance * Quality

    Args:
        df_prod (pd.DataFrame): DataFrame with production data.

    Returns:
        tuple[float, float, float, float]: A tuple containing oee, availability,
                                           performance, and quality scores.
    """
    # 1. Calculate Availability
    total_planned = df_prod['PLANNED_RUNTIME_HOURS'].sum()
    total_actual = df_prod['ACTUAL_RUNTIME_HOURS'].sum()
    
    if total_planned == 0:
        availability = 0.0
    else:
        availability = total_actual / total_planned
    
    # 2. Calculate Quality
    total_produced = df_prod['UNITS_PRODUCED'].sum()
    total_scrapped = df_prod['UNITS_SCRAPPED'].sum()
    
    if total_produced == 0:
        quality = 0.0
    else:
        quality = (total_produced - total_scrapped) / total_produced
    
    # 3. Calculate Performance (Simplified for this model)
    # In a real scenario, this would be: (Ideal Cycle Time * Total Count) / Actual Runtime
    performance = 0.95  # Using a fixed 95% as a stand-in for this dashboard
    
    # 4. Calculate Final OEE
    oee = availability * performance * quality
    
    return oee, availability, performance, quality