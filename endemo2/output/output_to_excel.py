from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from datetime import datetime
from collections import defaultdict
import os
import time
# import graphical output lazily to avoid heavy dependencies during exports
try:
    from endemo2.output.grapthical_output import GraphDataPreparer, Visualizer
except Exception:
    GraphDataPreparer = None
    Visualizer = None

class ExcelWriter:
    def __init__(self, data):
        # Create a timestamped output directory
        self.data = data
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.output_path = self._create_output_directory(data.input_manager)
        os.makedirs(self.output_path, exist_ok=True)
        # Data collection structures - separate regional and subregional data
        self.sector_forecasts = defaultdict(list)
        self.sector_forecasts_subregional = defaultdict(list)
        self.ue_sector_data = defaultdict(list)
        self.ue_sector_data_subregional = defaultdict(list)
        self.fe_sector_data = defaultdict(list)
        self.fe_sector_data_subregional = defaultdict(list)
        self.timeseries_data = defaultdict(list)
        self.efficiency = defaultdict(list)
        self.process_all(data)

    def _create_output_directory(self, input_manager) -> Path:
        """Create timestamped output directory using existing InputManager paths"""
        base_path = Path(input_manager.output_path)
        timestamped_path = base_path / self.timestamp
        timestamped_path.mkdir(parents=True, exist_ok=True)
        return timestamped_path


    def process_all(self, data):
        """Single method to handle full workflow"""
        self.collect_sector_forecasts(data)
        if data.input_manager.general_settings.UE_marker == 1:
            self.collect_ue_data(data.regions)
        if data.input_manager.general_settings.FE_marker == 1:
            self.collect_fe_data(data.regions)
        self.write_all_outputs()
        if self.data.input_manager.general_settings.graphical_out == 1:
            self._write_diagrams()

    def write_all_outputs(self):
        """Final method to write all collected data to Excel"""
        self._write_sector_forecasts()
        self._write_ue_sector_data()
        self._write_fe_sector_data()
        self._write_timeseries_data()

    def collect_ue_data(self, regions):
        """Collect useful energy data - both regional and subregional"""
        for region in regions:
            if region.energy_ue is not None and not region.energy_ue.empty:
                self._process_region_ue(region)
                # Also create subregional UE data
                self._process_region_ue_subregional(region)

    def collect_fe_data(self, regions):
        """Collect final energy data - both regional and subregional."""
        for region in regions:
            # Always collect regional FE data
            if region.energy_fe is not None and not region.energy_fe.empty:
                self._process_region_fe(region)
            
            # Collect subregional FE data if available
            if (hasattr(region, 'energy_fe_subregions') and 
                region.energy_fe_subregions is not None and 
                not region.energy_fe_subregions.empty):
                self._process_region_fe_subregional(region)

    def _process_region_fe_subregional(self, region):
        """Process subregional FE data"""
        df_sub = region.energy_fe_subregions.copy()
        # Ensure the subregion column is named 'Subregions' and placed after 'Region'
        if 'Subregions' not in df_sub.columns:
            alt = next((c for c in df_sub.columns if c.lower() in ('subregions', 'subregion')), None)
            if alt:
                df_sub = df_sub.rename(columns={alt: 'Subregions'})
            else:
                df_sub['Subregions'] = df_sub['Region']
        # Reorder columns
        cols = list(df_sub.columns)
        if 'Region' in cols:
            cols.remove('Region')
            cols.insert(0, 'Region')
        if 'Subregions' in cols:
            cols.remove('Subregions')
            cols.insert(1, 'Subregions')
        df_sub = df_sub[cols]
        for sector_name, sector_df in df_sub.groupby('Sector'):
            self.fe_sector_data_subregional[sector_name].append(sector_df)

    def _process_region_ue(self, region):
        """Process region-level UE data"""
        df = region.energy_ue
        for sector_name, sector_df in df.groupby('Sector'):
            self.ue_sector_data[sector_name].append(sector_df)

    def _process_region_ue_subregional(self, region):
        """Process subregional UE data by expanding using subregion factors"""
        df = region.energy_ue.copy()
        subregion_rows = []
        year_columns = [col for col in df.columns if isinstance(col, str) and col.isdigit()]
        
        for _, row in df.iterrows():
            sector = row.get('Sector', 'default')
            subsector = row.get('Subsector', 'default')
            
            factors = self.data.get_subregion_factors(region.region_name, sector, subsector)
            if not factors:
                sub_row = row.copy()
                sub_row['Subregions'] = region.region_name
                subregion_rows.append(sub_row)
                continue
            
            for subregion, factor in factors.items():
                sub_row = row.copy()
                sub_row['Subregions'] = subregion
                for year_col in year_columns:
                    if year_col in sub_row.index and pd.notna(sub_row[year_col]):
                        sub_row[year_col] = sub_row[year_col] * factor
                subregion_rows.append(sub_row)
        
        if subregion_rows:
            df_sub = pd.DataFrame(subregion_rows).reset_index(drop=True)
            # Reorder columns
            cols = list(df_sub.columns)
            if 'Region' in cols:
                cols.remove('Region')
                cols.insert(0, 'Region')
            if 'Subregions' in cols:
                cols.remove('Subregions')
                cols.insert(1, 'Subregions')
            df_sub = df_sub[cols]
            for sector_name, sector_df in df_sub.groupby('Sector'):
                self.ue_sector_data_subregional[sector_name].append(sector_df)

    def _process_region_fe(self, region):
        """Process region-level FE data (no subregional breakdown)"""
        df = region.energy_fe.copy()
        for sector_name, sector_df in df.groupby('Sector'):
            self.fe_sector_data[sector_name].append(sector_df)

    def collect_sector_forecasts(self, data):
        """Collect forecast data from model_forecast structure"""
        if data.efficiency_data:
            v1, v2 = data.efficiency_data
            forecast_eff = v1.forecast
            forecast_share = v2.forecast
            self.efficiency[v1.name].append(forecast_eff)
            self.efficiency[v2.name].append(forecast_share)
        for region in data.regions:
            for sector in region.sectors:
                for subsector in sector.subsectors:
                    self._process_subsector_data(region, sector, subsector)

    def _process_subsector_data(self, region, sector, subsector):
        """Process subsector-level data"""
        # Handle ECU forecast
        if subsector.ecu.forecast is not None:
            self._add_forecast_entry(
                region, sector, subsector,
                subsector.ecu, None
            )
        # Handle technology forecasts
        for tech in subsector.technologies:
            for var in tech.ddets:
                if var.forecast is not None:
                    self._add_forecast_entry(
                        region, sector, subsector,
                        var, tech.name
                    )

    # Intensive variables that should NOT be expanded to subregions
    # These are ratios, shares, or per-unit values that apply equally across subregions
    INTENSIVE_VARIABLE_PREFIXES = (
        'SPEC_EN',      # Specific energy per unit (GJ/ton, GJ/m², etc.)
        'SPEC_CAPA',    # Specific capacity
        'TECH_SHARE',   # Technology share (fraction)
        'MODAL_SPLIT',  # Modal share
        'MODAL_DRIVE',  # Drive share within modal
        'INEFF',        # Inefficiency factor
        'CALIB',        # Calibration factor
        'TEMP_DIFF',    # Temperature difference factor
        'OTHER_',       # Other factors (OTHER_CH, OTHER_NM)
    )
    
    def _is_intensive_variable(self, variable_name):
        """Check if a variable is intensive (ratio/share) vs extensive (quantity)."""
        return variable_name.startswith(self.INTENSIVE_VARIABLE_PREFIXES)

    def _add_forecast_entry(self, region, sector, subsector, variable, technology):
        """Format and store a forecast entry - both regional and subregional.
        Intensive variables (ratios, shares, specific energy) are not expanded to subregions."""
        df = variable.forecast.copy()
        df.columns = df.columns.astype(str)
        
        # Reorder columns for regional data
        column_order_regional = ["Region", 'Subsector', 'Variable', "Technology", "UE_Type", "FE_Type", 
                                  "Temp_level", "Subtech", "Drive"] + \
                                 [col for col in df.columns if col not in ["Region", 'Subsector', 'Variable', 
                                  "Technology", "UE_Type", "FE_Type", "Temp_level", "Subtech", "Drive"]]
        # Store regional forecast
        df_regional = df[[c for c in column_order_regional if c in df.columns]]
        self.sector_forecasts[sector.name].append(df_regional)
        
        # Skip subregional expansion for intensive variables
        # These are region-level parameters that apply equally to all subregions
        if self._is_intensive_variable(variable.name):
            return
        
        # Disaggregate extensive variables to subregions
        df_sub = self.data.expand_forecast_to_subregions(
            df, 
            region.region_name,
            sector.name,
            subsector.name
        )
        
        # Reorder columns for subregional data
        column_order_sub = ["Region", "Subregions", 'Subsector', 'Variable', "Technology", "UE_Type", 
                            "FE_Type", "Temp_level", "Subtech", "Drive"] + \
                           [col for col in df_sub.columns if col not in ["Region", "Subregions", 'Subsector', 
                            'Variable', "Technology", "UE_Type", "FE_Type", "Temp_level", "Subtech", "Drive"]]
        if 'Subregions' not in df_sub.columns:
            df_sub['Subregions'] = df_sub['Region']
        df_sub = df_sub[[c for c in column_order_sub if c in df_sub.columns]]
        self.sector_forecasts_subregional[sector.name].append(df_sub)

    def _write_sector_forecasts(self):
        """Handle sector forecast writing - both regional and subregional"""
        sector_dir = self.output_path / "sector_forecasts"
        sector_dir.mkdir(exist_ok=True)
        
        # Write regional forecasts
        for sector_name, dfs in self.sector_forecasts.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                file_path = sector_dir / f"predictions_{sector_name}.xlsx"
                combined.to_excel(file_path, index=False)
        
        # Write subregional forecasts
        for sector_name, dfs in self.sector_forecasts_subregional.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                file_path = sector_dir / f"predictions_{sector_name}_subregional.xlsx"
                combined.to_excel(file_path, index=False)

        for name, df in self.efficiency.items():
            if not all(x is None for x in df):
                combined = pd.concat(df, ignore_index=True)
                file_path = sector_dir / f"predictions_{name}.xlsx"
                combined.to_excel(file_path, index=False)

    def _write_timeseries_data(self):
        if self.data.input_manager.general_settings.timeseries_forecast == 0:
            return
        print("Starting timeseries export...")
        start_time = time.time()
        self._write_timeseries_results()
        if self.data.input_manager.general_settings.timeseries_per_region == 1:
            directory = self.output_path / "timeseries"
            directory.mkdir(exist_ok=True)
            self._write_per_region_timeseries(directory)
        print(f"Timeseries export completed in {time.time() - start_time:.2f}s")

    def _write_timeseries_results(self):
        output_path = self.output_path / "timeseries_total.xlsx"
        metadata = []
        yearly_data = {}  # {year: {header: [values]}}
        for region in self.data.regions:
            if not hasattr(region, 'timeseries_results') or not region.timeseries_results['profiles']:
                continue
            for pid, pdata in region.timeseries_results['profiles'].items():
                comp = pdata['components']
                # Add to metadata sheet (unchanged)
                metadata.append({
                    'Region': region.code,
                    'Profile ID': pid,
                    **comp,
                    'Sectors': ', '.join(pdata['contributors']['sectors']),
                    'Subsectors': ', '.join(pdata['contributors']['subsectors']),
                    'Techs': ', '.join(pdata['contributors']['technologies']),
                    'Subtechs': ', '.join(pdata['contributors']['subtechs']),
                    'Drives': ', '.join(pdata['contributors']['drives'])
                })
                # Process yearly data in column format
                for yr, ydata in pdata['years'].items():
                    if yr not in yearly_data:
                        yearly_data[yr] = {}
                    # Create column header
                    ue_type = comp['ue_type'].capitalize()
                    if ue_type == "Heat":
                        header = f"{region.code}.{ue_type}_{comp['temp_level']}"
                    else:
                        header = f"{region.code}.{ue_type}"
                    # Create column data
                    column_data = [
                        ydata['annual_energy']  # Third row: annual value
                    ]
                    # Add hourly values (8760 rows)
                    column_data.extend(ydata['hourly_values'])
                    yearly_data[yr][header] = column_data
            # Write to Excel
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Write metadata sheet
            if metadata:
                pd.DataFrame(metadata).to_excel(writer, sheet_name="Metadata", index=False)
            # Write yearly sheets
            for year, columns in yearly_data.items():
                # Create DataFrame
                max_length = max(len(col) for col in columns.values())
                data = {header: col + [None] * (max_length - len(col))
                        for header, col in columns.items()}
                df = pd.DataFrame(data)
                new_column = ["total"] + [str(i) for i in range(1, 8761)]
                df.insert(0, "Country_code.Commodity", new_column)
                # Write to sheet named after the year
                df.to_excel(writer, sheet_name=str(year), index=False)


    def _write_per_region_timeseries(self,directory):
        def process_region(region):
            if not any(getattr(s, 'timeseries_results', {}).get('profiles') for s in region.sectors):
                return
            output_path = directory / f"{region.region_name}.xlsx"
            metadata = []
            timeseries_data = []
            for sector in region.sectors:
                if not getattr(sector, 'timeseries_results', {}).get('profiles'):
                    continue
                for pid, pdata in sector.timeseries_results['profiles'].items():
                    # Use pre-parsed components if available
                    comp = pdata['components']
                    metadata.append({
                        'Sector': sector.name,
                        'Profile ID': pid,
                        **comp,
                        'Subsectors': ', '.join(pdata['contributors']['subsectors']),
                        'Techs': ', '.join(pdata['contributors']['technologies']),
                        'Subtechs': ', '.join(pdata['contributors']['subtechs']),
                        'Drives': ', '.join(pdata['contributors']['drives'])
                    })
                    # Process data in bulk per profile
                    for yr, ydata in pdata['years'].items():
                        hours = range(1, len(ydata['hourly_values']) + 1)
                        for hour in hours:
                            timeseries_data.append({
                                'Sector': sector.name,
                                'Profile': pid,
                                'Hour': hour,
                                'Year': yr,
                                'Value': ydata['hourly_values'][hour - 1],
                                **comp
                            })
                        # Annual total
                        timeseries_data.append({
                            'Sector': sector.name,
                            'Profile': pid,
                            'Hour': 'Annual Total',
                            'Year': yr,
                            'Value': ydata['annual_energy'],
                            **comp
                        })
            # Write to Excel
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                if metadata:
                    pd.DataFrame(metadata).to_excel(writer, sheet_name="Metadata", index=False)
                if timeseries_data:
                    df = pd.DataFrame(timeseries_data)
                    self._write_large_excel(df, writer, "Timeseries")
        # Parallel execution
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count())) as executor:
            list(executor.map(process_region, self.data.regions))

    def _write_large_excel(self, df, writer, base_sheet_name):
        """Modified writer that handles unsorted data"""
        max_rows = 1_000_000
        chunks = (len(df) // max_rows) + 1
        for i in range(chunks):
            chunk = df.iloc[i * max_rows: (i + 1) * max_rows]
            sheet_name = f"{base_sheet_name}_part{i + 1}" if chunks > 1 else base_sheet_name
            # Ensure header only on first chunk
            chunk.to_excel(
                writer,
                sheet_name=sheet_name[:31],
                index=False,
                header=(i == 0),
                startrow=0 if i == 0 else 1
            )

    def _write_ue_sector_data(self):
        """Handle sector-level UE data writing - both regional and subregional"""
        # Write regional UE files
        for sector_name, dfs in self.ue_sector_data.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                file_path = self.output_path / f"UE_{sector_name}.xlsx"
                with pd.ExcelWriter(file_path) as writer:
                    combined.to_excel(writer, sheet_name="UE_all")
                    combined.groupby(['UE_Type', "Temp_level", "Region"]).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Sector_per_Region")
                    combined.groupby(['UE_Type', "Temp_level", 'Subsector', 'Technology']).sum(
                        numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Technology")
                    combined.groupby(['UE_Type', "Temp_level", 'Subsector']).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Subsector")
                    combined.groupby(['UE_Type', "Temp_level", 'Sector']).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Sector")
        
        # Write subregional UE files (only first two sheets)
        for sector_name, dfs in self.ue_sector_data_subregional.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                file_path = self.output_path / f"UE_{sector_name}_subregional.xlsx"
                with pd.ExcelWriter(file_path) as writer:
                    combined.to_excel(writer, sheet_name="UE_all", index=False)
                    combined.groupby(['UE_Type', "Temp_level", "Region", "Subregions"]).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Subregion")

    def _write_fe_sector_data(self):
        """Handle sector-level FE data writing - both regional and subregional"""
        # Write regional FE files
        for sector_name, dfs in self.fe_sector_data.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                column_order = ["Region", 'Subsector', "Technology", "UE_Type", "FE_Type", "Temp_level", "Subtech",
                                "Drive"] + \
                               [col for col in combined.columns if
                                col not in ["Region", 'Subsector', "Technology", "UE_Type", "FE_Type",
                                            "Temp_level", "Subtech", "Drive"]]
                combined = combined[[c for c in column_order if c in combined.columns]]
                file_path = self.output_path / f"FE_{sector_name}.xlsx"
                with pd.ExcelWriter(file_path) as writer:
                    combined.to_excel(writer, sheet_name="FE_all", index=False)
                    combined.groupby(["FE_Type", 'UE_Type', "Temp_level", "Region"]).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Sector_per_Region")
                    combined.groupby(["FE_Type", 'UE_Type', "Temp_level", 'Subsector', 'Technology']).sum(
                        numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Technology")
                    combined.groupby(["FE_Type", 'UE_Type', "Temp_level", 'Subsector']).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Subsector")
                    combined.groupby(["FE_Type", 'UE_Type', "Temp_level", 'Sector']).sum(numeric_only=True).to_excel(
                        writer, sheet_name="Aggregated_by_Sector")
        
        # Write subregional FE files (only first two sheets)
        for sector_name, dfs in self.fe_sector_data_subregional.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                column_order = ["Region", 'Subregions', 'Subsector', "Technology", "UE_Type", "FE_Type", "Temp_level", 
                                "Subtech", "Drive"] + \
                               [col for col in combined.columns if
                                col not in ["Region", 'Subregions', 'Subsector', "Technology", "UE_Type", "FE_Type",
                                            "Temp_level", "Subtech", "Drive"]]
                combined = combined[[c for c in column_order if c in combined.columns]]
                file_path = self.output_path / f"FE_{sector_name}_subregional.xlsx"
                with pd.ExcelWriter(file_path) as writer:
                    combined.to_excel(writer, sheet_name="FE_all", index=False)
                    combined.groupby(["FE_Type", 'UE_Type', "Temp_level", "Region", "Subregions"]).sum(
                        numeric_only=True).to_excel(writer, sheet_name="Aggregated_by_Subregion")

    def _write_diagrams(self):
        """Generate and save Sankey diagrams"""
        # Prepare data
        plot_data_preparer = GraphDataPreparer(self.data)
        plot_data = plot_data_preparer.prepare_data()
        # Create visualizations
        visualizer = Visualizer(plot_data)
        visualizer.create_interactive_dashboard()