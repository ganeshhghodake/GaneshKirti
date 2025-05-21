import streamlit as st
import pandas as pd
import boto3
import io
import json
from datetime import datetime
from botocore.exceptions import ClientError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

st.set_page_config(layout="wide")
# st.title("🧀 GaneshKirti Milk Parlor")
st.title("🧀 Inventory Management")

# AWS S3 Configuration
region_name = "us-east-1"
bucket_name = "sfdr-rag"
s3 = boto3.client('s3', region_name=region_name)

# Files
inventory_file = 'inventory.csv'
sales_file = 'sales.csv'
orders_file = 'orders.csv'
products_file = 'products.json'

# Units and Status options
units = ["kg", "ltr", "nos"]
status_options = ["Pending", "Completed", "Cancelled"]

# --- Products Management via S3 ---
def load_products():
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=products_file)
        return json.loads(obj['Body'].read().decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            default_products = {
                "Dahi": "kg", "Basundi": "ltr", "Lassi": "ltr", "Pedha": "nos",
                "BadamShek": "ltr", "GulabJamun": "nos", "Paneer": "kg",
                "Shrikhand": "kg", "Milk": "ltr", "Butter": "kg"
            }
            save_products(default_products)
            return default_products
        else:
            raise

def save_products(products_dict):
    s3.put_object(Bucket=bucket_name, Key=products_file, Body=json.dumps(products_dict))

products = load_products()

# --- File Initializers ---
def ensure_file_exists(file_name, columns):
    try:
        s3.head_object(Bucket=bucket_name, Key=file_name)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            df = pd.DataFrame(columns=columns)
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            s3.put_object(Bucket=bucket_name, Key=file_name, Body=csv_buffer.getvalue())

ensure_file_exists(inventory_file, ['Date', 'Product', 'Quantity', 'Unit', 'Price', 'Total'])
ensure_file_exists(sales_file, ['Date', 'Product', 'Quantity', 'Unit', 'Price', 'Total'])
ensure_file_exists(orders_file, ['Date', 'Product', 'Quantity', 'Unit', 'Price', 'Total', 'Party', 'Advance', 'Status'])

# --- Data Helpers ---
def load_data(file_name):
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=file_name)
        return pd.read_csv(io.BytesIO(obj['Body'].read()))
    except Exception:
        return pd.DataFrame()

def save_data(df, file_name):
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=csv_buffer.getvalue())

# --- AGGrid Viewer ---
def show_aggrid(df, editable_cols=None, height=400, return_df=False):
    if df.empty:
        st.info("No data available.")
        return pd.DataFrame() if return_df else None

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(filter=True, sortable=True, resizable=True)

    for col in df.columns:
        gb.configure_column(col, filter='agSetColumnFilter')

    if editable_cols:
        for col in editable_cols:
            if col == "Status":
                gb.configure_column(col, editable=True, cellEditor='agSelectCellEditor',
                                    cellEditorParams={'values': status_options})
            else:
                gb.configure_column(col, editable=True)

    grid_options = gb.build()

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        enable_enterprise_modules=False,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        height=height,
        allow_unsafe_jscode=True,
        reload_data=False
    )
    return grid_response['data'] if return_df else None

# --- Sidebar Nav ---
if "page" not in st.session_state:
    st.session_state.page = "Reports"

page = st.sidebar.radio("Go to", ["Reports", "Inventory", "Sales", "Orders", "Add Products"])
st.session_state.page = page

# --- Pages ---
if page == "Reports":
    st.header("📊 Report")

    inventory_df = load_data(inventory_file)
    sales_df = load_data(sales_file)
    orders_df = load_data(orders_file)

    for df in [inventory_df, sales_df, orders_df]:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.date

    start_date = st.date_input("Start Date", datetime.now().date())
    end_date = st.date_input("End Date", datetime.now().date())

    product_filter = st.selectbox("Filter by Product", ["All Products"] + list(products.keys()))

    def filter_df(df):
        filtered = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
        if product_filter != "All Products":
            filtered = filtered[filtered["Product"] == product_filter]
        return filtered

    filtered_inventory = filter_df(inventory_df)
    filtered_sales = filter_df(sales_df)
    filtered_orders = filter_df(orders_df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 Inventory Cost ₹", f"{filtered_inventory['Total'].sum():.2f}")
    with col2:
        st.metric("📈 Total Sales Cost ₹", f"{filtered_sales['Total'].sum():.2f}")
    with col3:
        st.metric("📦 Inventory Added Qty", f"{filtered_inventory['Quantity'].sum():.2f}")
    with col4:
        st.metric("🛒 Total Orders Qty", f"{filtered_orders['Quantity'].sum():.2f}")

    st.markdown("### 📦 Inventory")
    show_aggrid(filtered_inventory)
    st.markdown("### 💵 Sales")
    show_aggrid(filtered_sales)
    st.markdown("### 📋 Orders")
    show_aggrid(filtered_orders)

elif page == "Inventory":
    st.header("📦 Inventory Management")
    products = load_products()
    inventory_df = load_data(inventory_file)

    with st.form("inventory_form"):
        col1, col2 = st.columns(2)
        with col1:
            product = st.selectbox("Product", list(products.keys()))
        with col2:
            default_unit = products.get(product, "kg")
            unit = st.selectbox("Unit", units, index=units.index(default_unit))
        quantity = st.number_input("Quantity", min_value=0.0, format="%.2f")
        price = st.number_input("Price per Unit ₹", min_value=0.0, format="%.2f")
        submit = st.form_submit_button("Add Inventory")
        if submit:
            total = quantity * price
            new_row = pd.DataFrame([[datetime.now().date(), product, quantity, unit, price, total]],
                                   columns=["Date", "Product", "Quantity", "Unit", "Price", "Total"])
            inventory_df = pd.concat([inventory_df, new_row], ignore_index=True)
            save_data(inventory_df, inventory_file)
            st.success("Inventory added successfully.")
            st.rerun()

    st.markdown("### Inventory Records")
    show_aggrid(inventory_df)

elif page == "Sales":
    st.header("💵 Sales")
    products = load_products()
    sales_df = load_data(sales_file)

    with st.form("sales_form"):
        col1, col2 = st.columns(2)
        with col1:
            product = st.selectbox("Product", list(products.keys()))
        with col2:
            default_unit = products.get(product, "kg")
            unit = st.selectbox("Unit", units, index=units.index(default_unit))
        quantity = st.number_input("Quantity", min_value=0.0, format="%.2f")
        price = st.number_input("Price per Unit ₹", min_value=0.0, format="%.2f")
        submit = st.form_submit_button("Add Sale")
        if submit:
            total = quantity * price
            new_row = pd.DataFrame([[datetime.now().date(), product, quantity, unit, price, total]],
                                   columns=["Date", "Product", "Quantity", "Unit", "Price", "Total"])
            sales_df = pd.concat([sales_df, new_row], ignore_index=True)
            save_data(sales_df, sales_file)
            st.success("Sale added successfully.")
            st.rerun()

    st.markdown("### Sales Records")
    show_aggrid(sales_df)

elif page == "Orders":
    st.header("📋 Orders")
    products = load_products()
    orders_df = load_data(orders_file)

    with st.form("orders_form"):
        col1, col2 = st.columns(2)
        with col1:
            product = st.selectbox("Product", list(products.keys()))
        with col2:
            default_unit = products.get(product, "kg")
            unit = st.selectbox("Unit", units, index=units.index(default_unit))
        quantity = st.number_input("Quantity", min_value=0.0, format="%.2f")
        price = st.number_input("Price per Unit ₹", min_value=0.0, format="%.2f")
        party = st.text_input("Party Name")
        advance = st.number_input("Advance Received ₹", min_value=0.0, format="%.2f")
        submit = st.form_submit_button("Add Order")
        if submit:
            total = quantity * price
            status = "Pending"
            new_row = pd.DataFrame([[datetime.now().date(), product, quantity, unit, price, total, party, advance, status]],
                                   columns=["Date", "Product", "Quantity", "Unit", "Price", "Total", "Party", "Advance", "Status"])
            orders_df = pd.concat([orders_df, new_row], ignore_index=True)
            save_data(orders_df, orders_file)
            st.success("Order added successfully.")
            st.rerun()

    st.markdown("### Orders Records (Status Editable)")
    updated_df = show_aggrid(orders_df, editable_cols=["Status"], return_df=True)
    if updated_df is not None and not updated_df.equals(orders_df):
        save_data(updated_df, orders_file)
        st.success("Order status updated.")

elif page == "Add Products":
    st.header("🧾 Product Master")
    products = load_products()
    product_df = pd.DataFrame(list(products.items()), columns=["Product", "Default Unit"])

    st.markdown("### 🧺 Existing Products")
    st.dataframe(product_df, use_container_width=True)

    with st.form("add_product_form"):
        st.markdown("### ➕ Add New Product")
        col1, col2 = st.columns(2)
        with col1:
            new_product = st.text_input("Product Name")
        with col2:
            new_unit = st.selectbox("Default Unit", units)
        submit = st.form_submit_button("Add Product")
        if submit:
            if new_product.strip() == "":
                st.error("Product name cannot be empty.")
            elif new_product in products:
                st.warning("Product already exists.")
            else:
                products[new_product] = new_unit
                save_products(products)
                st.success(f"Product '{new_product}' added with unit '{new_unit}'.")
                st.rerun()
