"""
Subregional disaggregation module.

This module contains functions to expand regional energy forecasts
to subregional (NUTS-2) level using distribution factors.
"""
import pandas as pd


def expand_ue_to_subregions(region, data_manager, forecast_year_range):
    """
    Expand useful energy to subregions by multiplying by normalized subregion factors.
    Creates one row per subregion with the Subregions column set to subregion code
    and values scaled by the subregion factor. Region column keeps the region name.
    
    Args:
        region: Region instance with energy_ue data
        data_manager: DataManager instance with subregion factors
        forecast_year_range: List of forecast years
    """
    if region.energy_ue is None or region.energy_ue.empty:
        return
    
    subregion_rows = []
    year_columns = [str(year) for year in forecast_year_range]
    
    for _, ue_row in region.energy_ue.iterrows():
        sector = ue_row.get('Sector')
        subsector = ue_row.get('Subsector')
        
        # Get subregion factors using distribution variable from settings
        factors = data_manager.get_subregion_factors(region.region_name, sector, subsector)
        
        # If no factors, keep original region data
        if not factors:
            subregion_rows.append(ue_row.copy())
            continue
        
        # Create one row per subregion with scaled values
        for subregion, factor in factors.items():
            sub_row = ue_row.copy()
            sub_row['Subregions'] = subregion
            for year_col in year_columns:
                if year_col in sub_row.index and pd.notna(sub_row[year_col]):
                    sub_row[year_col] = sub_row[year_col] * factor
            subregion_rows.append(sub_row)
    
    if subregion_rows:
        region.energy_ue_subregions = pd.DataFrame(subregion_rows).reset_index(drop=True)


def expand_forecast_to_subregions(data_manager, forecast_df, region_name, sector_name=None, subsector_name=None):
    """
    Expand forecast data to subregions using normalized factors.
    
    Args:
        data_manager: DataManager instance with subregion factors
        forecast_df: DataFrame with forecast data
        region_name: Name of the region to disaggregate
        sector_name: Sector name (for factor lookup)
        subsector_name: Subsector name (for factor lookup)
    
    Returns:
        DataFrame with subregional breakdown or original if no factors available
    """
    if forecast_df is None or forecast_df.empty:
        return forecast_df
    
    subregion_rows = []
    
    for _, row in forecast_df.iterrows():
        sector = sector_name or row.get('Sector', 'default')
        subsector = subsector_name or row.get('Subsector', 'default')
        
        # Get subregion factors using the distribution variable from settings
        factors = data_manager.get_subregion_factors(region_name, sector, subsector)
        
        # If no factors found, keep original row
        if not factors:
            subregion_rows.append(row.copy())
            continue
        
        # Create one row per subregion with scaled values
        year_columns = [col for col in forecast_df.columns if isinstance(col, str) and col.isdigit()]
        
        for subregion, factor in factors.items():
            sub_row = row.copy()
            sub_row['Subregions'] = subregion
            for year_col in year_columns:
                if year_col in sub_row.index and pd.notna(sub_row[year_col]):
                    sub_row[year_col] = sub_row[year_col] * factor
            subregion_rows.append(sub_row)
    
    if subregion_rows:
        return pd.DataFrame(subregion_rows).reset_index(drop=True)
    else:
        return forecast_df


def expand_fe_to_subregions(region, data_manager, forecast_year_range):
    """
    Expand final energy to subregions by multiplying by normalized subregion factors.
    Creates one row per subregion with the Subregions column set to subregion code
    and values scaled by the subregion factor. Region column keeps the region name.
    
    Args:
        region: Region instance with energy_fe data
        data_manager: DataManager instance with subregion factors
        forecast_year_range: List of forecast years
    """
    if region.energy_fe is None or region.energy_fe.empty:
        return
    
    subregion_rows = []
    year_columns = [str(year) for year in forecast_year_range]
    
    for _, fe_row in region.energy_fe.iterrows():
        sector = fe_row.get('Sector')
        subsector = fe_row.get('Subsector')
        
        # Get subregion factors using distribution variable from settings
        factors = data_manager.get_subregion_factors(region.region_name, sector, subsector)
        
        # If no factors, keep original region data
        if not factors:
            subregion_rows.append(fe_row.copy())
            continue
        
        # Create one row per subregion with scaled values
        for subregion, factor in factors.items():
            sub_row = fe_row.copy()
            sub_row['Subregions'] = subregion
            for year_col in year_columns:
                if year_col in sub_row.index and pd.notna(sub_row[year_col]):
                    sub_row[year_col] = sub_row[year_col] * factor
            subregion_rows.append(sub_row)
    
    if subregion_rows:
        region.energy_fe_subregions = pd.DataFrame(subregion_rows).reset_index(drop=True)
