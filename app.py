import streamlit as st
import asyncio
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import re
from pathlib import Path
from fastmcp import Client

# Page configuration
st.set_page_config(
    page_title="Energy Invoice Analyzer",
    page_icon="⚡",
    layout="wide"
)

# Initialize MCP client
@st.cache_resource
def get_mcp_client():
    return Client("http://127.0.0.1:8000/mcp")

async def read_pdf_async(path: str):
    """Read PDF using MCP server"""
    client = get_mcp_client()
    async with client:
        result = await client.call_tool("read_local_pdf", {"path": path})
        # Convert CallToolResult to dict
        if hasattr(result, 'content'):
            return result.content[0].text if result.content else {}
        return result

async def list_pdfs_async(directory: str):
    """List PDFs in directory using MCP server"""
    client = get_mcp_client()
    async with client:
        result = await client.call_tool("list_pdf_files", {"directory": directory})
        # Convert CallToolResult to dict
        if hasattr(result, 'content'):
            import json
            return json.loads(result.content[0].text) if result.content else {}
        return result

def parse_invoice_text(text: str) -> dict:
    """Extract structured data from invoice text"""
    data = {
        'period_start': None,
        'period_end': None,
        'electricity_cost': None,
        'gas_cost': None,
        'vat': None,
        'total_charges': None,
        'direct_debit': None,
        'starting_balance': None,
        'closing_balance': None,
        'electricity_kwh': None,
        'gas_kwh': None,
        'electricity_unit_rate': None,
        'gas_unit_rate': None,
        'electricity_standing_charge': None,
        'gas_standing_charge': None
    }
    
    # Extract billing period
    period_match = re.search(r'Your energy charges for (\d+\w+\s+\w+)\s*-\s*(\d+\w+\s+\w+\s+\d{4})', text)
    if period_match:
        data['period_start'] = period_match.group(1)
        
        def convert_date(date_string):
            """Convert date from '9th Oct 2024' to 'yyyy/mm/dd' format"""
            # Remove ordinal suffixes (st, nd, rd, th)
            date_cleaned = date_string.replace('st', '').replace('nd', '').replace('rd', '').replace('th', '')
    
            # Parse the date
            date_obj = datetime.strptime(date_cleaned, '%d %b %Y')
    
            # Format to yyyy/mm/dd
            return date_obj.strftime('%Y/%m/%d')
            
        data['period_end'] = convert_date(period_match.group(2))
    
    # Extract costs
    elec_match = re.search(r'Cost of electricity\s+£([\d.]+)', text)
    if elec_match:
        data['electricity_cost'] = float(elec_match.group(1))
    
    gas_match = re.search(r'Cost of gas\s+£([\d.]+)', text)
    if gas_match:
        data['gas_cost'] = float(gas_match.group(1))
    
    vat_match = re.search(r'VAT.*?£([\d.]+)', text)
    if vat_match:
        data['vat'] = float(vat_match.group(1))
    
    total_match = re.search(r'Total charges\s+£([\d.]+)', text)
    if total_match:
        data['total_charges'] = float(total_match.group(1))
    
    # Extract direct debit
    dd_match = re.search(r'Direct Debit.*?\+£([\d.]+)', text)
    if dd_match:
        data['direct_debit'] = float(dd_match.group(1))
    
    # Extract balances
    start_balance_match = re.search(r'Starting balance\s+£([\d.]+)\s+in\s+(debit|credit)', text)
    if start_balance_match:
        amount = float(start_balance_match.group(1))
        data['starting_balance'] = -amount if start_balance_match.group(2) == 'debit' else amount
    
    close_balance_match = re.search(r'Closing balance\s+£([\d.]+)\s+in\s+(debit|credit)', text)
    if close_balance_match:
        amount = float(close_balance_match.group(1))
        data['closing_balance'] = -amount if close_balance_match.group(2) == 'debit' else amount
    
    # Extract electricity consumption
    elec_kwh_match = re.search(r'Total units\s+([\d.]+)\s+kWh', text)
    if elec_kwh_match:
        data['electricity_kwh'] = float(elec_kwh_match.group(1))
    
    # Extract gas consumption (look for the second occurrence)
    gas_section = re.search(r'Gas in detail.*?Total units\s+([\d.]+)\s+kWh', text, re.DOTALL)
    if gas_section:
        data['gas_kwh'] = float(gas_section.group(1))
    
    # Extract rates
    elec_rate_match = re.search(r'Unit rate\s+([\d.]+)p per kWh', text)
    if elec_rate_match:
        data['electricity_unit_rate'] = float(elec_rate_match.group(1))
    
    elec_standing_match = re.search(r'Standing charge\s+([\d.]+)p a day', text)
    if elec_standing_match:
        data['electricity_standing_charge'] = float(elec_standing_match.group(1))
    
    # Extract gas rates (look in gas section)
    gas_section_full = re.search(r'Gas in detail.*?(?=Registered in England|$)', text, re.DOTALL)
    if gas_section_full:
        gas_text = gas_section_full.group(0)
        gas_rate_match = re.search(r'Unit rate\s+([\d.]+)p per kWh', gas_text)
        if gas_rate_match:
            data['gas_unit_rate'] = float(gas_rate_match.group(1))
        
        gas_standing_match = re.search(r'Standing charge\s+([\d.]+)p a day', gas_text)
        if gas_standing_match:
            data['gas_standing_charge'] = float(gas_standing_match.group(1))
    
    return data

def main():
    st.title("⚡ Energy Invoice Analyzer")
    st.markdown("Analyze your energy bills using AI-powered PDF extraction")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("📁 Configuration")
        
        # Directory input
        default_dir = "/Users/ola/SOFTWARE/MCP/pdf-reader/bills"
        invoice_dir = st.text_input(
            "Invoice Directory", 
            value=default_dir,
            help="Enter the path to your invoice directory"
        )
        
        st.markdown("---")
        st.markdown("### 📊 Server Status")
        try:
            # Test connection
            test_result = asyncio.run(list_pdfs_async(invoice_dir))
            if isinstance(test_result, dict) and test_result.get('success'):
                st.success("✅ MCP Server Connected")
                st.info(f"Found {test_result['data']['pdf_count']} PDF(s)")
            elif isinstance(test_result, dict):
                st.error("❌ Directory access error")
                st.error(test_result.get('message', 'Unknown error'))
            else:
                st.error("❌ Unexpected response format")
        except Exception as e:
            st.error("❌ Cannot connect to MCP server")
            st.error(f"Error: {str(e)}")
            st.info("Make sure server.py is running on port 8000")
    
    # Main content
    tab1, tab2, tab3 = st.tabs(["📄 Load Invoices", "📊 Analysis", "💾 Export Data"])
    
    with tab1:
        st.header("Load and Process Invoices")
        
        if st.button("🔍 Scan Directory for PDFs", type="primary"):
            with st.spinner("Scanning directory..."):
                try:
                    result = asyncio.run(list_pdfs_async(invoice_dir))
                    
                    if isinstance(result, dict) and result.get('success'):
                        files = result['data']['files']
                        st.success(f"Found {len(files)} PDF file(s)")
                        
                        if files:
                            # Display files
                            df_files = pd.DataFrame(files)
                            df_files['size_mb'] = (df_files['size_bytes'] / 1024 / 1024).round(2)
                            df_files['modified'] = pd.to_datetime(df_files['modified'], unit='s')
                            
                            st.dataframe(
                                df_files[['name', 'size_mb', 'modified']],
                                use_container_width=True,
                                hide_index=True
                            )
                            
                            # Store in session state
                            st.session_state['pdf_files'] = files
                    elif isinstance(result, dict):
                        st.error(f"Error: {result.get('message', 'Unknown error')}")
                    else:
                        st.error("Unexpected response format from server")
                        
                except Exception as e:
                    st.error(f"Error scanning directory: {str(e)}")
        
        # Process PDFs
        if 'pdf_files' in st.session_state and st.session_state['pdf_files']:
            st.markdown("---")
            if st.button("⚙️ Process All Invoices", type="primary"):
                files = st.session_state['pdf_files']
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                all_data = []
                
                for idx, file_info in enumerate(files):
                    status_text.text(f"Processing {file_info['name']}...")
                    
                    try:
                        result = asyncio.run(read_pdf_async(file_info['path']))
                        
                        # Parse JSON response if it's a string
                        if isinstance(result, str):
                            import json
                            result = json.loads(result)
                        
                        if isinstance(result, dict) and result.get('success'):
                            text = result['data']['text']
                            parsed_data = parse_invoice_text(text)
                            parsed_data['filename'] = file_info['name']
                            parsed_data['file_path'] = file_info['path']
                            all_data.append(parsed_data)
                        elif isinstance(result, dict):
                            st.warning(f"Failed to read {file_info['name']}: {result.get('message')}")
                        else:
                            st.warning(f"Unexpected response for {file_info['name']}")
                            
                    except Exception as e:
                        st.error(f"Error processing {file_info['name']}: {str(e)}")
                    
                    progress_bar.progress((idx + 1) / len(files))
                
                if all_data:
                    st.session_state['invoice_data'] = all_data
                    st.success(f"✅ Successfully processed {len(all_data)} invoice(s)")
                    status_text.text("Processing complete!")
                else:
                    st.error("No invoices were successfully processed")
    
    with tab2:
        st.header("Invoice Analysis")
        
        if 'invoice_data' not in st.session_state or not st.session_state['invoice_data']:
            st.info("👈 Please load and process invoices first")
        else:
            data = st.session_state['invoice_data']
            df = pd.DataFrame(data)
            
            # Summary metrics
            st.subheader("📈 Summary Metrics")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_electricity = df['electricity_cost'].sum()
                st.metric("Total Electricity", f"£{total_electricity:.2f}")
            
            with col2:
                total_gas = df['gas_cost'].sum()
                st.metric("Total Gas", f"£{total_gas:.2f}")
            
            with col3:
                total_charges = df['total_charges'].sum()
                st.metric("Total Charges", f"£{total_charges:.2f}")
            
            with col4:
                total_consumption = df['electricity_kwh'].sum() + df['gas_kwh'].sum()
                st.metric("Total Energy (kWh)", f"{total_consumption:.0f}")
            
            # Detailed breakdown
            st.markdown("---")
            st.subheader("📋 Invoice Details")
            
            display_df = df[[
                'period_end', 'electricity_cost', 'gas_cost', 
                'total_charges', 'electricity_kwh', 'gas_kwh'
            ]].copy()
            
            display_df.columns = ['Period End', 'Electricity (£)', 'Gas (£)', 
                                  'Total (£)', 'Electricity (kWh)', 'Gas (kWh)']
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Charts
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("💰 Cost Breakdown")
                
                # Stacked bar chart
                fig_cost = go.Figure()
                fig_cost.add_trace(go.Bar(
                    name='Electricity',
                    x=df['period_end'],
                    y=df['electricity_cost'],
                    marker_color='#FFA500'
                ))
                fig_cost.add_trace(go.Bar(
                    name='Gas',
                    x=df['period_end'],
                    y=df['gas_cost'],
                    marker_color='#4169E1'
                ))
                
                fig_cost.update_layout(
                    barmode='stack',
                    xaxis_title="Period",
                    yaxis_title="Cost (£)",
                    height=400,
                    showlegend=True
                )
                st.plotly_chart(fig_cost, use_container_width=True)
            
            with col2:
                st.subheader("⚡ Energy Consumption")
                
                # Consumption chart
                fig_consumption = go.Figure()
                fig_consumption.add_trace(go.Bar(
                    name='Electricity',
                    x=df['period_end'],
                    y=df['electricity_kwh'],
                    marker_color='#FFA500'
                ))
                fig_consumption.add_trace(go.Bar(
                    name='Gas',
                    x=df['period_end'],
                    y=df['gas_kwh'],
                    marker_color='#4169E1'
                ))
                
                fig_consumption.update_layout(
                    barmode='group',
                    xaxis_title="Period",
                    yaxis_title="Consumption (kWh)",
                    height=400,
                    showlegend=True
                )
                st.plotly_chart(fig_consumption, use_container_width=True)
            
            # Balance tracking
            if df['closing_balance'].notna().any():
                st.markdown("---")
                st.subheader("💳 Account Balance Trend")
                
                fig_balance = go.Figure()
                fig_balance.add_trace(go.Scatter(
                    x=df['period_end'],
                    y=df['closing_balance'],
                    mode='lines+markers',
                    line=dict(color='#32CD32', width=3),
                    marker=dict(size=8),
                    fill='tozeroy'
                ))
                
                fig_balance.add_hline(y=0, line_dash="dash", line_color="red", 
                                     annotation_text="Zero Balance")
                
                fig_balance.update_layout(
                    xaxis_title="Period",
                    yaxis_title="Balance (£)",
                    height=400
                )
                st.plotly_chart(fig_balance, use_container_width=True)
    
    with tab3:
        st.header("Export Data")
        
        if 'invoice_data' not in st.session_state or not st.session_state['invoice_data']:
            st.info("👈 Please load and process invoices first")
        else:
            df = pd.DataFrame(st.session_state['invoice_data'])
            
            st.subheader("📥 Download Options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # CSV export
                csv = df.to_csv(index=False)
                st.download_button(
                    label="📄 Download as CSV",
                    data=csv,
                    file_name="energy_invoices.csv",
                    mime="text/csv",
                    type="primary"
                )
            
            with col2:
                # Excel export
                import io
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Invoices', index=False)
                
                st.download_button(
                    label="📊 Download as Excel",
                    data=buffer.getvalue(),
                    file_name="energy_invoices.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
            
            st.markdown("---")
            st.subheader("📊 Preview")
            st.dataframe(df, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()