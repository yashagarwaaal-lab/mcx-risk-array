import pandas as pd # Pandas used for read file
import yfinance as yf # Yahoo Finance used for fetching stock historical data
import numpy as np # Numpy used for log calculation
from datetime import datetime, timedelta
import math 
from scipy.stats import norm #Used for getting z values of the confidence level
from pathlib import Path #Used for getting file paths
from scipy.stats import genpareto
import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
import xml.etree.ElementTree as ET
from lxml import etree
import pickle
import gzip
import glob
import os
from scipy.stats import norm
from scipy.optimize import brentq
from growwapi import GrowwAPI
from datetime import date
import streamlit as st
from datetime import date

#User Inputs
risk_free_rate=0.0608
#======================================================================================
#Grow access keys
user_api_key = os.getenv("GROWW_API_KEY")
user_secret = os.getenv("GROWW_SECRET")

access_token = GrowwAPI.get_access_token(api_key = user_api_key, secret = user_secret) 
groww = GrowwAPI(access_token)
#======================================================================================

#ltp_symbol = "MCX_GOLD27NOV26186500CE"
#current_price_response = groww.get_ltp(
#    segment=groww.SEGMENT_COMMODITY,
#    exchange_trading_symbols=ltp_symbol
#    )
#current_future_price=current_price_response[ltp_symbol]
#print(current_future_price)
#===================================================================================
#Defining paths for input and output
#input_path = "C:/Users/Python/Desktop/Tarun/Risk Array/Input" # Input path used for picking up the input files
#storage_path = "C:/Users/Python/Desktop/Tarun/Risk Array/Output" 
#folder = Path(input_path)

BASE_DIR = Path(__file__).parent
#======================================================================================
#Reading the ELM file
ELM_File_Path = next(BASE_DIR.glob("DailyMargin*"), None)
if not ELM_File_Path: 
    raise FileNotFoundError(fr"No Daily Margin file present in the folder location "+ input_path)

ELM_file = pd.read_csv(ELM_File_Path) 
#====================================================================================
#Converting the expiry date column in required format
ELM_file["Groww Symbol"]=""
ELM_file["Groww Symbol"] = ELM_file["Groww Symbol"].astype(str)
for i in range(len(ELM_file)):
    exp_date=str(ELM_file.loc[i,"Expiry Date"])
    day=exp_date[0:2]
    month=exp_date[2:5]
    year=exp_date[5:9]
    year_groww=exp_date[7:9]
    ELM_file.loc[i,"Groww Symbol"]="MCX_"+ELM_file.loc[i,"Symbol"]+day+month+year_groww+"FUT"
    month_dict={"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06","JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
    month=month_dict[month]
    exp_date=year+month+day
    ELM_file.loc[i,"Expiry Date"]=exp_date
#====================================================================================
#=====================================================================================
#Creating dictionaries
#List of underlying
underlying_list = ELM_file["Symbol"].unique()

#Creating Groww symbol dictionary
groww_symbol_dict = {}
for i in range(len(ELM_file)):
    groww_symbol_dict[ELM_file.loc[i, "Symbol"], ELM_file.loc[i, "Expiry Date"]] = ELM_file.loc[i, "Groww Symbol"]

#Creating a dictionary of futures and their respective expiry dates
futures_expiry_dict = {}
for underlying in underlying_list:  
    futures_expiry_dict[underlying] = ELM_file[ELM_file["Symbol"] == underlying]["Expiry Date"].unique().tolist()

#Creating a dictionary of futures and their span margins and elm margins
span_margin_percentage_dict = {}
elm_long_margin_percentage_dict = {}
elm_short_margin_percentage_dict = {}
for i in range(len(ELM_file)):
    key = (ELM_file.loc[i, "Symbol"], ELM_file.loc[i, "Expiry Date"])
    span_margin_percentage_dict[key] = float(ELM_file.loc[i, "Initial Margin(%)"])/100
    elm_long_margin_percentage_dict[key] = float(ELM_file.loc[i, "ELM Long (%)"])/100
    elm_short_margin_percentage_dict[key] = float(ELM_file.loc[i, "ELM Short (%)"])/100
#==================================================================================================================
#Reading span file
span_file_path = next(BASE_DIR.glob("MCXRPF*"), None)
tree = etree.parse(span_file_path)
root = tree.getroot()
#==================================================================================================================
#Creating Dictionaries from span file

#Dictionary for underlying price
underlying_price_dict={}
for phy in root.iter("phyPf"):
    name=phy.find("name").text
    for phy_1 in phy.findall("phy"):
        price_u=float(phy_1.find("p").text)
        underlying_price_dict[name] = price_u


#Futures risk array dictionary and futures price dictionary
futures_risk_array_dict={}
futures_price_dict={}
for fut in root.iter("futPf"):
    name=fut.find("name").text
    for fut_1 in fut.findall("fut"):
        sett_date=fut_1.find("setlDate").text
        price=float(fut_1.find("p").text)
        ra_element = fut_1.find("ra")
        risk_array = [float(a.text) for a in ra_element.findall("a")] if ra_element is not None else []
        futures_risk_array_dict[(name, sett_date)] = risk_array
        futures_price_dict[(name, sett_date)] = price

#Options and their expiry dates dictionary
options_expiry_dict = {}
for opt in root.iter("oofPf"):
    name=opt.find("name").text
    options_expiry_dict[name] = [series.find("setlDate").text for series in opt.findall("series")]

#Call Options risk array dictionary
call_name_expiry_strike={}
for opt in root.iter("oofPf"):
    name=opt.find("name").text
    for series in opt.findall("series"):
        expiry = series.find("setlDate").text
        time=float(series.find("t").text)
        for opt in series.findall("opt"):
            if opt.find("o").text =="C":
                strike = float(opt.find("k").text)
                price=float(opt.find("p").text)
                ca_element=opt.find("ra")
                d=float(ca_element.find("d").text)
                risk_array = [float(a.text) for a in ca_element.findall("a")] if ca_element is not None else []
                call_name_expiry_strike[(name,expiry,strike)]= {
                "Risk Array": risk_array,
                "Delta": d,
                "Price":price,
                "Time":time
            }

#Put Options risk array dictionary               
put_name_expiry_strike={}
for opt in root.iter("oofPf"):
    name=opt.find("name").text
    for series in opt.findall("series"):
        expiry = series.find("setlDate").text
        time=float(series.find("t").text)
        for opt in series.findall("opt"):
            if opt.find("o").text =="P":
                strike = float(opt.find("k").text)
                pa_element=opt.find("ra")
                price=float(opt.find("p").text)
                d=float(pa_element.find("d").text)
                risk_array = [float(a.text) for a in pa_element.findall("a")] if pa_element is not None else []
                put_name_expiry_strike[(name,expiry,strike)]= {
                "Risk Array": risk_array,
                "Delta": d,
                "Price":price,
                "Time":time
            }

#Creating spread margin dictionary

option_spread={}
for ccd in root.iter("ccDef"):
    name=ccd.find("name").text
    for tier2 in ccd.findall("somTiers"):
        for tier in tier2.findall("tier"):
            tn=float(tier.find("tn").text)
            date_s_1=tier.find("sPe").text
            date_e_1=tier.find("ePe").text
            val=float(tier.find("rate/val").text)
            option_spread[(name,date_s_1,date_e_1)]=val
#df = pd.DataFrame(list(option_spread.items()), columns=['Key', 'Value'])
#df.to_csv("C:/Users/Python/Desktop/Tarun/Risk Array/Output/Option_Spread.csv", index=False)


tn_name_date1_date2={}
for ccd in root.iter("ccDef"):
    name=ccd.find("name").text
    for tier1 in ccd.findall("interTiers"):
        for tier in ccd.findall("tier"):
            tn=float(tier.find("tn").text)
            date_s=tier.find("sPe").text
            date_e=tier.find("ePe").text
            tn_name_date1_date2[(name,tn)]=(date_s,date_e)


pleg_name={}
for ccd in root.iter("ccDef"):
    name=ccd.find("name").text
    for spread in ccd.findall("dSpread"):
        val=float(spread.find("rate/val").text)
        tn=float(spread.find("tLeg/tn").text)
        pleg_name[(name,tn)]=val

spread_name_date1_date2={}
for (name1, tn1), val in pleg_name.items():
    # Second loop: tn_name_date1_date2
    for (name2, tn2), (date_s, date_e) in tn_name_date1_date2.items():
        # Match condition
        if name1 == name2 and tn1 == tn2:
            spread_name_date1_date2[(name1, date_s, date_e)] = val
#=========================================================================================
#Metron model to calculate the price of option
def merton_price(S, K, T, r, q, sigma, option_type='C'):
#"""Calculates price using Spot and Dividend Yield."""
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'C':
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    elif option_type == 'P':
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)

#==========================================================================================
def calculate_iv_merton(target_price, S, K, T, r, q, option_type='C'):
        """Finds IV using Spot and Dividend."""
        func = lambda sigma: merton_price(S, K, T, r, q, sigma, option_type) - target_price
        try:
            if func(0.0001) * func(5.0) > 0:
                return 0.0            
            return brentq(func, 0.00000001, 5.0)
        except ValueError:
            return 0.0
#===================================================================================================================
def margin_calculator(Ticker,Side,Derivative_Type,Option_Type,Scenario,Specified_Price,Expiry_date, Strike_Price, Lot):
    scenario1="Margin as per SPAN File"
    scenario2="Current SPAN"
    scenario3="What if Analysis"
    ticker=Ticker.upper()
    if Scenario==scenario1:
        if Derivative_Type.lower()=="futures":
            span_margin_percentage=span_margin_percentage_dict[(ticker,Expiry_date)]
            risk_array=futures_risk_array_dict[(ticker,Expiry_date)]
            if Side.lower()=="buy":
                elm_margin_percentage=elm_long_margin_percentage_dict[(ticker,Expiry_date)]
                
            else:
                risk_array = [-val for val in risk_array]
                elm_margin_percentage=elm_short_margin_percentage_dict[(ticker,Expiry_date)]
            span_margin=np.max(risk_array)*Lot
            price=futures_price_dict[(ticker,Expiry_date)]
            elm_margin=price*elm_margin_percentage*Lot
            total_margin=span_margin+elm_margin
            premium=0

        elif Derivative_Type.lower()=="options":
            expiry_dates=futures_expiry_dict[ticker]
            
            min=10000000000
            for exp in expiry_dates:
                diff=abs(float(exp)-float(Expiry_date))
                if diff<min:
                    min=diff
                    future_date=exp
            
            price_fut=futures_price_dict[(ticker,future_date)]
            span_part1=option_spread[(ticker,Expiry_date,Expiry_date)]

            if Side.lower()=="buy":
                elm_margin_percentage=elm_long_margin_percentage_dict[(ticker,future_date)]
            else:
                elm_margin_percentage=elm_short_margin_percentage_dict[(ticker,future_date)]


            if Option_Type.lower()=="call":
                risk_array=call_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Risk Array"]
                d=call_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Delta"]
                price=call_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Price"]
            else:
                risk_array=put_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Risk Array"]
                d=put_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Delta"]
                price=put_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Price"]
            span_margin=(span_part1+price)*Lot
            elm_margin=(price_fut+price)*elm_margin_percentage*Lot
            premium=price*Lot
            total_margin=span_margin+elm_margin
            if Side.lower()=="buy":
                span_margin=0
                elm_margin=0
                total_margin=0
    
    #Current Span
    elif Scenario==scenario2:
        if Derivative_Type.lower()=="futures":
            current_price_symbol=groww_symbol_dict[(ticker,Expiry_date)]
            current_price_response = groww.get_ltp(
            segment=groww.SEGMENT_COMMODITY,
            exchange_trading_symbols=current_price_symbol
            )
            current_future_price=current_price_response[current_price_symbol]

            span_margin_percentage=span_margin_percentage_dict[(ticker,Expiry_date)]
            price_scan_range=float(current_future_price)*float(span_margin_percentage)

            risk_array=[]
            risk_array1=0
            risk_array2=0
            risk_array3=round(price_scan_range/3)*-1
            risk_array4=round(price_scan_range/3)*-1
            risk_array5=round(price_scan_range/3)*1
            risk_array6=round(price_scan_range/3)*1
            risk_array7=round(price_scan_range*2/3)*-1
            risk_array8=round(price_scan_range*2/3)*-1
            risk_array9=round(price_scan_range*2/3)*1
            risk_array10=round(price_scan_range*2/3)*1
            risk_array11=round(price_scan_range)*-1
            risk_array12=round(price_scan_range)*-1
            risk_array13=round(price_scan_range)*1
            risk_array14=round(price_scan_range)*1
            risk_array15=round(price_scan_range*2*0.45)*-1
            risk_array16=round(price_scan_range*2*0.45)*1
            risk_array=[risk_array1,risk_array2,risk_array3,risk_array4,risk_array5,risk_array6,risk_array7,risk_array8,risk_array9,risk_array10,risk_array11,risk_array12,risk_array13,risk_array14,risk_array15,risk_array16]

            if Side.lower()=="buy":
                elm_margin_percentage=elm_long_margin_percentage_dict[(ticker,Expiry_date)]
                
            else:
                risk_array = [-val for val in risk_array]
                elm_margin_percentage=elm_short_margin_percentage_dict[(ticker,Expiry_date)]
            span_margin=np.max(risk_array)*Lot
            price=futures_price_dict[(ticker,Expiry_date)]
            elm_margin=price*elm_margin_percentage*Lot
            total_margin=span_margin+elm_margin
            premium=0

        elif Derivative_Type.lower()=="options":
            expiry_dates=futures_expiry_dict[ticker]
            
            min=10000000000
            for exp in expiry_dates:
                diff=abs(float(exp)-float(Expiry_date))
                if diff<min:
                    min=diff
                    future_date=exp
            
            current_price_symbol=groww_symbol_dict[(ticker,future_date)]
            current_price_response = groww.get_ltp(
            segment=groww.SEGMENT_COMMODITY,
            exchange_trading_symbols=current_price_symbol
            )
            current_future_price=current_price_response[current_price_symbol]
            span_margin_percentage=span_margin_percentage_dict[(ticker,future_date)]

            span_part1=float(current_future_price)*float(span_margin_percentage)

            if Side.lower()=="buy":
                elm_margin_percentage=elm_long_margin_percentage_dict[(ticker,future_date)]
            else:
                elm_margin_percentage=elm_short_margin_percentage_dict[(ticker,future_date)]

            #MCX_GOLD27NOV26186500CE
            year_ex=Expiry_date[0:4]
            month_ex=Expiry_date[4:6]
            day_ex=Expiry_date[6:8]
            month_dict={"01":"JAN","02":"FEB","03":"MAR","04":"APR","05":"MAY","06":"JUN","07":"JUL","08":"AUG","09":"SEP","10":"OCT","11":"NOV","12":"DEC"}
            month_ex=month_dict[month_ex]   
            
            if Option_Type.lower()=="call":
                risk_array=call_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Risk Array"]
                d=call_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Delta"]
                price=call_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Price"]
                current_option_symbol="MCX_"+ticker+day_ex+month_ex+year_ex[2:4]+str(Strike_Price)+"CE"
            else:
                risk_array=put_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Risk Array"]
                d=put_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Delta"]
                price=put_name_expiry_strike[(ticker,Expiry_date,Strike_Price)]["Price"]
                current_option_symbol="MCX_"+ticker+day_ex+month_ex+year_ex[2:4]+str(Strike_Price)+"PE"
            opt_price_response = groww.get_ltp(
                segment=groww.SEGMENT_COMMODITY,
                exchange_trading_symbols=current_option_symbol
                )
            price=opt_price_response[current_option_symbol]
            span_margin=(span_part1+price)*Lot
            elm_margin=(current_future_price+price)*elm_margin_percentage*Lot
            premium=price*Lot
            total_margin=span_margin+elm_margin
            if Side.lower()=="buy":
                span_margin=0
                elm_margin=0
                total_margin=0
                premium=-1*premium
    
    elif Scenario==scenario3:
        if Derivative_Type.lower()=="futures":
            if "gold" in ticker.lower() or "silver" in ticker.lower() or "elec" in ticker.lower():
                underlying_price=underlying_price_dict[ticker]
                futures_price=futures_price_dict[(ticker,Expiry_date)]
                current_future_price=Specified_Price*futures_price/underlying_price
                                
            else:    
                expiry_dates=futures_expiry_dict[ticker]
                
                min=10000000000
                for exp in expiry_dates:
                    diff=abs(float(exp)-float(Expiry_date))
                    if diff<min:
                        min=diff
                        future_date=exp
                
                if float(Expiry_date)>float(future_date):
                    current_price_symbol=groww_symbol_dict[(ticker,future_date)]
                    current_price_response = groww.get_ltp(
                    segment=groww.SEGMENT_COMMODITY,
                    exchange_trading_symbols=current_price_symbol
                    )
                    current_future_price=current_price_response[current_price_symbol]
                    future_price_symbol=groww_symbol_dict[(ticker,Expiry_date)]
                    future_price_response = groww.get_ltp(
                    segment=groww.SEGMENT_COMMODITY,
                    exchange_trading_symbols=future_price_symbol
                    )
                    future_future_price=future_price_response[future_price_symbol]
                    current_future_price=Specified_Price*future_future_price/current_future_price
                else:
                    current_future_price=float(Specified_Price)

            span_margin_percentage=span_margin_percentage_dict[(ticker,Expiry_date)]
            price_scan_range=float(current_future_price)*float(span_margin_percentage)

            risk_array=[]
            risk_array1=0
            risk_array2=0
            risk_array3=round(price_scan_range/3)*-1
            risk_array4=round(price_scan_range/3)*-1
            risk_array5=round(price_scan_range/3)*1
            risk_array6=round(price_scan_range/3)*1
            risk_array7=round(price_scan_range*2/3)*-1
            risk_array8=round(price_scan_range*2/3)*-1
            risk_array9=round(price_scan_range*2/3)*1
            risk_array10=round(price_scan_range*2/3)*1
            risk_array11=round(price_scan_range)*-1
            risk_array12=round(price_scan_range)*-1
            risk_array13=round(price_scan_range)*1
            risk_array14=round(price_scan_range)*1
            risk_array15=round(price_scan_range*2*0.45)*-1
            risk_array16=round(price_scan_range*2*0.45)*1
            risk_array=[risk_array1,risk_array2,risk_array3,risk_array4,risk_array5,risk_array6,risk_array7,risk_array8,risk_array9,risk_array10,risk_array11,risk_array12,risk_array13,risk_array14,risk_array15,risk_array16]

            if Side.lower()=="buy":
                elm_margin_percentage=elm_long_margin_percentage_dict[(ticker,Expiry_date)]
                
            else:
                risk_array = [-val for val in risk_array]
                elm_margin_percentage=elm_short_margin_percentage_dict[(ticker,Expiry_date)]
            span_margin=np.max(risk_array)*Lot
            price=futures_price_dict[(ticker,Expiry_date)]
            elm_margin=price*elm_margin_percentage*Lot
            total_margin=span_margin+elm_margin
            premium=0

        elif Derivative_Type.lower()=="options":
            if "gold" in ticker.lower() or "silver" in ticker.lower() or "elec" in ticker.lower():
                current_price=Specified_Price
                underlying_price=underlying_price_dict[ticker]
                futures_price=futures_price_dict[(ticker,Expiry_date)]
                current_future_price=Specified_Price*futures_price/underlying_price
            else:
                expiry_dates=futures_expiry_dict[ticker]
                
                min=10000000000
                for exp in expiry_dates:
                    diff=abs(float(exp)-float(Expiry_date))
                    if diff<min:
                        min=diff
                        future_date=exp
                
                if float(Expiry_date)>float(future_date):
                    current_price_symbol=groww_symbol_dict[(ticker,future_date)]
                    current_price_response = groww.get_ltp(
                    segment=groww.SEGMENT_COMMODITY,
                    exchange_trading_symbols=current_price_symbol
                    )
                    current_future_price=current_price_response[current_price_symbol]
                    future_price_symbol=groww_symbol_dict[(ticker,Expiry_date)]
                    future_price_response = groww.get_ltp(
                    segment=groww.SEGMENT_COMMODITY,
                    exchange_trading_symbols=future_price_symbol
                    )
                    future_future_price=future_price_response[future_price_symbol]
                    current_future_price=Specified_Price*future_future_price/current_future_price
                else:
                    current_future_price=float(Specified_Price)

                span_file_spot_price=underlying_price_dict[ticker]
                span_file_future_price=futures_price_dict[(ticker,Expiry_date)]
                current_price=span_file_spot_price*float(Specified_Price)/span_file_future_price

                
            relevant_call_strike=[]
            for name, expiry, strike,time in call_name_expiry_strike:
                if name==ticker and expiry==Expiry_date and strike<=current_price:
                    time_opt=time
                    iv=calculate_iv_merton(call_name_expiry_strike(name, expiry, strike, time)["Price"],current_price , strike, time,risk_free_rate, 0, option_type='C')
                    relevant_call_strike.append((float(strike),iv))

            relevant_put_strike=[]
            for name, expiry, strike, time in put_name_expiry_strike:
                if name==ticker and expiry==Expiry_date and strike>Strike_Price:
                    time_opt=time
                    iv=calculate_iv_merton(put_name_expiry_strike(name, expiry, strike, time)["Price"],current_price , strike, time,risk_free_rate, 0, option_type='P')
                    relevant_put_strike.append((float(strike),iv))
            
            combined_strikes = sorted(relevant_call_strike + relevant_put_strike, key=lambda x: x[0])
            # Extract the entire 1st column (Strike Prices) -> index 0
            strike_column = [item[0] for item in combined_strikes]

            # Extract the entire 2nd column (IV Values) -> index 1
            iv_column = [item[1] for item in combined_strikes]

            curve_fit=np.polyfit(strike_column,iv_column,2)
            iv_option=np.polyval(curve_fit, float(Strike_Price))

            if Option_Type.lower()=="call":
                opt_type='C'
            else:
                opt_type='P'
            ltp_option=merton_price(current_price,Strike_Price,time_opt,risk_free_rate,0,iv_option,option_type=opt_type)

            span_part1=float(current_future_price)*float(span_margin_percentage)

            if Side.lower()=="buy":
                elm_margin_percentage=elm_long_margin_percentage_dict[(ticker,future_date)]
            else:
                elm_margin_percentage=elm_short_margin_percentage_dict[(ticker,future_date)]

            span_margin=(span_part1+ltp_option)*Lot
            elm_margin=(current_future_price+ltp_option)*elm_margin_percentage*Lot
            premium=ltp_option*Lot
            total_margin=span_margin+elm_margin
            if Side.lower()=="buy":
                span_margin=0
                elm_margin=0
                total_margin=0
                premium=-1*premium

    return premium,span_margin,elm_margin,total_margin
#===========================================================================================================
#User Inputs
#Ticker="CRUDEOILM"
#Side="Sell"
#Derivative_Type="futures"
#Option_Type="Call"
#Scenario="Margin as per SPAN File"#Margin as per SPAN File,Current SPAN,What if Analysis 
#Specified_price=0
#Expiry_date="20260819"
#Strike_Price=9500
#Lot=10

#premium,span_margin,elm_margin,total_margin=margin_calculator(Ticker,Side,Derivative_Type,Option_Type,Scenario,Specified_price,Expiry_date,Strike_Price,Lot)
#print("Premium:", premium)
#print("SPAN Margin:", span_margin)  
#print("ELM Margin:", elm_margin)
#print("Total Margin:", total_margin)

#========================================================================================================
st.set_page_config(
    page_title="MCX Margin Calculator",
    page_icon="📈",
    layout="wide"
)

st.title("📈 MCX Margin Calculator")
st.caption("Single Position Margin Calculator")

st.markdown("---")

# ==============================================================================
# INPUT SECTION
# ==============================================================================

col1, col2 = st.columns(2)

with col1:

    scenario = st.selectbox(
        "Scenario",
        [
            "Margin as per SPAN File",
            "Current SPAN",
            "What if Analysis"
        ]
    )

    ticker = st.selectbox(
        "Underlying",
        sorted(underlying_list)
    )

    derivative = st.selectbox(
        "Derivative Type",
        [
            "Futures",
            "Options"
        ]
    )

    side = st.selectbox(
        "Position",
        [
            "Buy",
            "Sell"
        ]
    )

with col2:

    expiry = st.selectbox(
        "Expiry",
        futures_expiry_dict[ticker],
        format_func=lambda x: datetime.strptime(
            x,
            "%Y%m%d"
        ).strftime("%d-%b-%Y")
    )

    option_type = ""
    strike = 0

    if derivative == "Options":

        option_type = st.selectbox(
            "Option Type",
            [
                "Call",
                "Put"
            ]
        )

        if option_type == "Call":

            strike_list = sorted([
                strike
                for (name, exp, strike) in call_name_expiry_strike.keys()
                if name == ticker and exp == expiry
            ])

        else:

            strike_list = sorted([
                strike
                for (name, exp, strike) in put_name_expiry_strike.keys()
                if name == ticker and exp == expiry
            ])

        strike = st.selectbox(
            "Strike Price",
            strike_list
        )

    lots = st.number_input(
        "Lots",
        min_value=1,
        value=1,
        step=1
    )

specified_price = 0.0

if scenario == "What if Analysis":

    specified_price = st.number_input(
        "Specified Underlying Price",
        min_value=0.0,
        value=0.0,
        step=1.0
    )

st.markdown("---")

calculate = st.button(
    "🚀 Calculate Margin",
    use_container_width=True
)

# ==============================================================================
# CALCULATE
# ==============================================================================

if calculate:

    with st.spinner("Calculating Margin..."):

        premium, span_margin, elm_margin, total_margin = margin_calculator(
            Ticker=ticker,
            Side=side,
            Derivative_Type=derivative,
            Option_Type=option_type,
            Scenario=scenario,
            Specified_Price=specified_price,
            Expiry_date=expiry,
            Strike_Price=strike,
            Lot=lots
        )

    st.success("Calculation Completed Successfully")

    st.markdown("---")

    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric(
            "Premium",
            f"₹ {premium:,.2f}"
        )

    with m2:
        st.metric(
            "SPAN Margin",
            f"₹ {span_margin:,.2f}"
        )

    with m3:
        st.metric(
            "ELM Margin",
            f"₹ {elm_margin:,.2f}"
        )

    with m4:
        st.metric(
            "Total Margin",
            f"₹ {total_margin:,.2f}"
        )

    st.markdown("---")

    st.subheader("Position Summary")

    summary = pd.DataFrame({

        "Field": [
            "Underlying",
            "Derivative",
            "Position",
            "Scenario",
            "Expiry",
            "Option Type",
            "Strike",
            "Lots",
            "Specified Price"
        ],

        "Value": [
            ticker,
            derivative,
            side,
            scenario,
            expiry,
            option_type if derivative == "Options" else "-",
            strike if derivative == "Options" else "-",
            lots,
            specified_price if scenario == "What if Analysis" else "-"
        ]

    })

    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True
    )

    csv = summary.to_csv(index=False)

    st.download_button(
        "📥 Download Summary",
        csv,
        file_name="Margin_Calculation.csv",
        mime="text/csv",
        use_container_width=True
    )

#python -m streamlit run "Streamlit Mcx.py"
#cd "C:\Users\Python\Desktop\Tarun\Risk Array"
