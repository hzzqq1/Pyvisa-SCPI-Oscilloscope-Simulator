import numpy as np
import altair as alt
import pyvisa as py
import streamlit as st
import pyvisa_py
import pandas as pd 


if "rm" not in st.session_state:
    st.session_state["rm"] = py.ResourceManager("osc.yaml@sim") 
    
if "osc" not in st.session_state:
    st.session_state["osc"] = st.session_state["rm"].open_resource("ASRL1::INSTR")
    st.session_state["osc"].read_termination = "\n"
    st.session_state["osc"].write_termination = "\n"

if "mul" not in st.session_state:
    st.session_state["mul"] = st.session_state["rm"].open_resource("USB::0x1111::0x2222::0x1234::INSTR")
    st.session_state["mul"].read_termination = "\n"
    st.session_state["mul"].write_termination = "\n"

if "gen" not in st.session_state:
    st.session_state["gen"] = st.session_state["rm"].open_resource("ASRL2::INSTR")
    st.session_state["gen"].read_termination = "\n"
    st.session_state["gen"].write_termination = "\n"

if "psu" not in st.session_state:
    st.session_state["psu"] = st.session_state["rm"].open_resource("GPIB0::5::INSTR")
    st.session_state["psu"].read_termination = "\n"
    st.session_state["psu"].write_termination = "\n"


if "osc_wave" not in st.session_state:
    st.session_state["osc_wave"] = []

if "osc_noise" not in st.session_state:
    st.session_state["osc_noise"] = 0

if "mul_history" not in st.session_state:
    st.session_state["mul_history"] = []

if "mul_sample_point" not in st.session_state:
    st.session_state["mul_sample_point"] = 0



if "state" not in st.session_state:
    st.session_state["state"] = "STOPPED"

if "cmd_status" not in st.session_state:
    st.session_state["cmd_status"] = ("info", "Ready. Enter a SCPI command and click Send.")

if "phase_different" not in st.session_state:
    st.session_state["phase_different"] = 0.00



st.set_page_config(layout="wide")
#select_device = st.selectbox("select device", ["Oscilloscope", "Multimeter", "Signal generator", "DC power supply"])
device_options = {
    "📈 Oscilloscope": "Oscilloscope",
    "📟 Multimeter": "Multimeter",
    "〰️ Signal generator": "Signal generator",
    "🔋 DC power supply": "DC power supply"
}

selected_label = st.segmented_control(
    "Select Instrument",
    options=list(device_options.keys()),
    default="📈 Oscilloscope",
    selection_mode="single",
    label_visibility="collapsed"  
)

select_device = device_options[selected_label] if selected_label else "Oscilloscope"


left_col, right_col = st.columns([2, 1])
def get_psu_real_output(psu_dev, load_resistance=20.0):
            out_state = psu_dev.query(":OUTPut?").strip()
            v_set = float(psu_dev.query(":VOLTage?"))
            i_limit = float(psu_dev.query(":CURRent?"))

            if out_state in ["OFF", "0"]:
                v_actual, i_actual, mode = 0.0, 0.0, "OFF"
            else:
                i_required = v_set / load_resistance
                if i_required > i_limit:
                    i_actual = i_limit
                    v_actual = i_limit * load_resistance
                    mode = "CC (Current Limited)"
                else:
                    v_actual = v_set
                    i_actual = i_required
                    mode = "CV (Constant Voltage)"

            psu_dev.write(f"INTERNAL:PSU:VOLT {v_actual:.4f}")
            psu_dev.write(f"INTERNAL:PSU:CURR {i_actual:.4f}")
            return v_actual, i_actual, mode, load_resistance



def execute_scpi_command(device_name, dev_obj, raw_cmd):
    cmd = raw_cmd.strip()
    cmd_upper = cmd.upper()
    if not cmd:
        return "warning", "Please enter a SCPI command first."

    try:
        if device_name == "Oscilloscope":
            if cmd_upper == ":RUN":
                st.session_state["state"] = "RUNNING"
                return "success", "Oscilloscope -> :RUN (Started)"
            elif cmd_upper == ":STOP":
                st.session_state["state"] = "STOPPED"
                return "success", "Oscilloscope -> :STOP (Stopped)"
            elif cmd_upper == ":SINGLE":
                st.session_state["state"] = "PAUSED"
                return "success", "Oscilloscope -> :SINGle (Single Capture)"

        if device_name == "Multimeter":
            if cmd_upper.startswith(":CONF"):
                dev_obj.write(cmd)
                if "VOLT" in cmd_upper and "AC" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC VOLT:AC")
                elif "VOLT" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC VOLT:DC")
                elif "CURR" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC CURR:DC")
                elif "RES" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC RES")
                st.session_state["mul_history"] = []
                return "success", f"Configured Mode -> {dev_obj.query(':CONFigure?')}"

            elif ":RANGE " in cmd_upper and "AUTO" not in cmd_upper:
                dev_obj.write(cmd)
                dev_obj.write(":VOLTage:DC:RANGe:AUTO OFF")
                return "success", f"Manual Range Set -> {cmd.split()[-1]}V (Auto OFF)"

            elif cmd_upper.startswith(":MEAS"):
                #dev_obj.write("INTERNAL:SET:FUNC VOLT:DC")
                #dev_obj.write(":VOLTage:DC:RANGe:AUTO ON")
                # 立即计算一次最新值返回，即使在 STOPPED 状态下也能测出结果！
                #v_psu, _, _, _ = get_psu_real_output(st.session_state["psu"])
                #val_str = f"{v_psu:+.5E}"
                #dev_obj.write(f"INTERNAL:SET:READING {val_str}")
                #return "success", f"Measure Result: {val_str} V"
                v_psu, i_psu, _, r_load = get_psu_real_output(st.session_state["psu"])
                
                if "VOLT" in cmd_upper and "AC" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC VOLT:AC")
                    val = abs(float(np.random.normal(0.005, 0.001))) if v_psu > 0 else 0.0
                    unit = "V (AC)"
                elif "CURR" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC CURR:DC")
                    val = i_psu
                    unit = "A"
                elif "RES" in cmd_upper:
                    dev_obj.write("INTERNAL:SET:FUNC RES")
                    val = r_load
                    unit = "Ω"
                else:  
                    dev_obj.write("INTERNAL:SET:FUNC VOLT:DC")
                    dev_obj.write(":VOLTage:DC:RANGe:AUTO ON")
                    val = v_psu
                    unit = "V"

                val_str = f"{val:+.5E}"
                dev_obj.write(f"INTERNAL:SET:READING {val_str}")
                return "success", f"Measure Result: {val_str} {unit}"


        if "?" in cmd:
            result = dev_obj.query(cmd)
            return "success", f"Query [{cmd}] => {result}"
        else:
            dev_obj.write(cmd)
            return "success", f"Command [{cmd}] Executed Successfully!"

    except Exception as e:
        return "error", f"SCPI / VISA Error: {e}"



with right_col:
   
    device_map = {
        "Oscilloscope": st.session_state["osc"],
        "Multimeter": st.session_state["mul"],
        "Signal generator": st.session_state["gen"],
        "DC power supply": st.session_state["psu"]
    }
    current_dev = device_map[select_device]

    st.subheader("💻 SCPI Command Console")
    with st.form(key="scpi_form", clear_on_submit=False):
        input_command = st.text_input("Enter SCPI Command (e.g., *IDN?, :MEASure:AVERage? VPP,CHANnel1)")
        submitted = st.form_submit_button("Send Command", use_container_width=True)
        if submitted:
            status_type, status_msg = execute_scpi_command(select_device, current_dev, input_command)
            st.session_state["cmd_status"] = (status_type, status_msg)
            st.toast(status_msg) 


    s_type, s_msg = st.session_state["cmd_status"]
    if s_type == "success":
        st.success(s_msg)
    elif s_type == "error":
        st.error(s_msg)
    elif s_type == "warning":
        st.warning(s_msg)
    else:
        st.info(s_msg)

    st.markdown("---")


    col_buton1, col_buton2 = st.columns(2)
    with col_buton1:
        btn_start_label = "Resume" if st.session_state["state"] == "PAUSED" else "Generate"
        if st.button(btn_start_label, use_container_width=True, disabled=(st.session_state["state"] == "RUNNING")):
            st.session_state["state"] = "RUNNING"
            st.rerun()

    with col_buton2:
        if st.session_state["state"] == "RUNNING":
            if st.button("Pause", use_container_width=True):
                st.session_state["state"] = "PAUSED"
                st.rerun()
        elif st.session_state["state"] == "PAUSED":
            if st.button("Stop (Clear)", use_container_width=True):
                st.session_state["state"] = "STOPPED"
                st.session_state["phase_different"] = 0.00
                st.session_state["osc_wave"] = []
                st.session_state["mul_history"] = []
                st.session_state["mul_sample_count"] = 0
                st.rerun()
        else:
            st.button("Stopped", use_container_width=True, disabled=True)

    if st.button("Reset", use_container_width=True):
        if select_device in ["Oscilloscope", "Signal generator"]:
            st.session_state["state"] = "STOPPED"
            st.session_state["osc_wave"] = []
            st.session_state["phase_different"] =0.00
            st.session_state["osc_noise"] = 0.00
            gen_dev = st.session_state["gen"]
            osc_dev = st.session_state["osc"]
            gen_dev.write(":FREQuency 200")
            gen_dev.write(":VOLTage 2.0")
            gen_dev.write(":VOLTage:OFFSet 1.5")
            osc_dev.write(":CHANnel1:SCALe 1.0")
            osc_dev.write(":CHANnel1:OFFSet 0.0")
            osc_dev.write(":CHANnel1:COUPling DC")
            osc_dev.write(":TIMebase:MAIN:SCALe 0.001")
            osc_dev.write(":TRIGger:EDGe:LEVel 0.0")
            st.rerun()
        if select_device in ["Multimeter", "DC power supply"]:
            st.session_state["state"] = "STOPPED"
            st.session_state["mul_history"] = []
            st.session_state["mul_sample_count"] = 0
            mul_dev = st.session_state["mul"]
            psu_dev = st.session_state["psu"]
            mul_dev.write(":VOLTage:DC:RANGe:AUTO ON")
            mul_dev.write(":VOLTage:DC:RANGe 10.0")
            mul_dev.write("INTERNAL:SET:FUNC VOLT:DC")
            mul_dev.write("INTERNAL:SET:READING +0.00000E+00")
            psu_dev.write(":OUTPut ON")
            psu_dev.write(":VOLTage 5.0")
            psu_dev.write(":CURRent 1.0")
            psu_dev.write("INTERNAL:PSU:VOLT 5.0")
            psu_dev.write("INTERNAL:PSU:CURR 0.25")
            st.rerun()
            

with left_col:
    if select_device in ["Oscilloscope", "Signal generator"]:
        refresh_seconded = 0.5 if st.session_state["state"] == "RUNNING" else None

        if st.session_state["state"] in ["RUNNING", "PAUSED"] :
            @st.fragment(run_every= refresh_seconded)
            def wave_generated_common():

                osc_dev = st.session_state["osc"]
                gen_dev = st.session_state["gen"]


                signal_freq = float(gen_dev.query(":FREQuency?"))
                signal_amp = float(gen_dev.query(":VOLTage?"))
                dc_bias = float(gen_dev.query(":VOLTage:OFFSet?"))

                disp = osc_dev.query(":CHANnel1:DISPlay?").strip()
                if disp in ["OFF", "0"]:
                    return None, 0, 0 
                v_scale = float(osc_dev.query(":CHANnel1:SCALe?"))
                v_offset = float(osc_dev.query(":CHANnel1:OFFSet?"))
                coupling = osc_dev.query(":CHANnel1:COUPling?").strip()
                t_scale = float(osc_dev.query(":TIMebase:MAIN:SCALe?"))
                trig_lvl = float(osc_dev.query(":TRIGger:EDGe:LEVel?"))

                total_time = 10.0 * t_scale
                t = np.linspace(0, total_time, 100, endpoint=False)
                
                if (dc_bias - signal_amp) <= trig_lvl <= (dc_bias + signal_amp):
                    norm_lvl = np.clip((trig_lvl - dc_bias) / signal_amp, -1.0, 1.0)
                    phase = np.arcsin(norm_lvl)
                else:
                    if st.session_state["state"] == "RUNNING":
                        st.session_state["phase_different"] += 0.8
                        phase = st.session_state["phase_different"]
                    else:
                        phase = 0.00
                        
                if st.session_state["state"] =="RUNNING":
                    noise = np.random.normal(0, 0.05, len(t))
                    st.session_state["osc_noise"] = noise  
                else:
                    noise = st.session_state["osc_noise"]
                raw_wave = signal_amp * np.sin(2 * np.pi * signal_freq * t + phase) + dc_bias + noise
                st.session_state["osc_wave"].append(raw_wave)
                if len(st.session_state["osc_wave"]) > 50:
                    st.session_state["osc_wave"].pop(0)
                
                if coupling == "AC":
                    processed_wave = raw_wave - np.mean(raw_wave) 
                elif coupling == "GND":
                    processed_wave = np.zeros_like(raw_wave)      
                else:
                    processed_wave = raw_wave                     

                vpp = float(np.max(processed_wave) - np.min(processed_wave))
                osc_dev.write(f"INTERNAL:SET:VPP {vpp:.3f}")
                osc_dev.write(f"INTERNAL:SET:FREQ {signal_freq:.1f}")
                with st.container(border=True):
                    y_min = v_offset - 4.0 * v_scale
                    y_max = v_offset + 4.0 * v_scale
                    
                    df = pd.DataFrame({"Time (s)": t, "Voltage (V)": processed_wave})
                    chart = alt.Chart(df).mark_line(color="#00FFAA", strokeWidth=2).encode(
                        x=alt.X("Time (s)", title=f"Time ({t_scale*1000:.2f} ms/div)"),
                        y=alt.Y("Voltage (V)", scale=alt.Scale(domain=[y_min, y_max]), title=f"Voltage ({v_scale} V/div)")
                    ).properties(height=400)
                    st.altair_chart(chart, use_container_width=True)

            wave_generated_common()



    if select_device in ["Multimeter", "DC power supply"]:

        refresh_seconded = 1 if st.session_state["state"] == "RUNNING" else None
        if st.session_state["state"] in ["RUNNING", "PAUSED"]:
            @st.fragment(run_every=refresh_seconded)
            def multimeter_common():
                try:
                    mul_dev = st.session_state["mul"]
                    psu_dev = st.session_state["psu"]

                    v_psu, i_psu, psu_mode, r_load = get_psu_real_output(psu_dev, load_resistance=20.0)

                    current_mode = mul_dev.query(":CONFigure?").strip().strip('"')
                    auto_range = mul_dev.query(":VOLTage:DC:RANGe:AUTO?").strip()
                    manual_range = float(mul_dev.query(":VOLTage:DC:RANGe?"))

                    noise = np.random.normal(0, 0.002) 
                    is_overload = False

                    if current_mode == "VOLT:DC":
                        raw_val = float(v_psu + noise) if v_psu > 0 else 0.0
                        unit = "V (DC)"
                        if auto_range in ["OFF", "0"] and abs(raw_val) > manual_range:
                            is_overload = True
                    elif current_mode == "VOLT:AC":
                        raw_val = abs(float(np.random.normal(0.005, 0.001))) if v_psu > 0 else 0.0
                        unit = "V (AC Ripple)"
                    elif current_mode == "CURR:DC":
                        raw_val = float(i_psu + noise / 10.0) if i_psu > 0 else 0.0
                        unit = "A (DC)"
                    else:  
                        raw_val = float(r_load + noise * 10.0)
                        unit = "Ω (Load)"

                    if is_overload:
                        scpi_str = "+9.90000E+37"  
                        display_text = "OVERLOAD (+9.90000E+37)"
                        plot_val = None  
                    else:
                        scpi_str = f"{raw_val:+.5E}"
                        display_text = f"{raw_val:.4f} {unit}   |   SCPI: {scpi_str}"
                        plot_val = round(raw_val, 4)

                    mul_dev.write(f"INTERNAL:SET:READING {scpi_str}")

                    if st.session_state["state"] == "RUNNING" and plot_val is not None:
                        st.session_state["mul_sample_count"] += 1
                        st.session_state["mul_history"].append({
                            "Sample": st.session_state["mul_sample_count"],
                            "Value": plot_val
                        })
                        if len(st.session_state["mul_history"]) > 60:
                            st.session_state["mul_history"].pop(0)

                    st.metric(
                        label=f"HP 34401A Digital Multimeter [{current_mode}]",
                        value=display_text,
                        delta=f"Range: {'AUTO' if auto_range in ['ON', '1'] else f'{manual_range}V'}"
                        )
                    
                    if len(st.session_state["mul_history"]) > 0:
                        with st.container(border=True):
                            df = pd.DataFrame(st.session_state["mul_history"])
                            chart = alt.Chart(df).mark_line(point=True, color="#FFA500").encode(
                                x=alt.X("Sample:Q", axis=alt.Axis(tickMinStep=1, title="Sample Count (Points)")),
                                y=alt.Y("Value:Q", scale=alt.Scale(zero=False), title=f"Measured Value ({unit})")
                            ).properties(height=340)
                            st.altair_chart(chart, use_container_width=True)

                except Exception as e:
                    st.error(f"Multimeter Error: {e}")
            multimeter_common()

    if select_device in ["Oscilloscope", "Signal generator"]:
        gen_dev = st.session_state["gen"]
        osc_dev = st.session_state["osc"]
        signal_freq = float(gen_dev.query(":FREQuency?"))
        signal_amp = float(gen_dev.query(":VOLTage?"))
        dc_bias = float(gen_dev.query(":VOLTage:OFFSet?"))
        v_scale = float(osc_dev.query(":CHANnel1:SCALe?"))
        v_offset = float(osc_dev.query(":CHANnel1:OFFSet?"))
        coupling = osc_dev.query(":CHANnel1:COUPling?").strip()
        t_scale = float(osc_dev.query(":TIMebase:MAIN:SCALe?"))
        trig_lvl = float(osc_dev.query(":TRIGger:EDGe:LEVel?"))
        mean_vpp = float(osc_dev.query(":MEASure:AVERage? VPP,CHANnel1"))
        #data = {
            #"Signal Generator Frequency": signal_freq,
            #"Maxium voltage": signal_amp, 
            #"Central Offset": dc_bias,
            #"Vertical V/Div": v_scale,
            #"Channel Offset": v_offset,
            #"Coupling Of wave": coupling,
            #"Horizontal Sec/Div": t_scale,
            #"Mean VPP Voltage": mean_vpp
        #}

        #with st.container(border=True):

            #for i, (key, value) in enumerate(data.items()):
                #col1, col2 = st.columns([1, 2])
                #with col1:
                    #st.markdown(f"**{key}**") 
                #with col2:
                    #st.markdown(f"{value}")  

  
                #if i < len(data) - 1:
                    #st.divider()
        df_params = pd.DataFrame({
            "Parameter": [
                "Signal Generator Frequency", "Maximum Voltage", "Central Offset",
                "Vertical V/Div", "Channel Offset", "Coupling Of Wave",
                "Horizontal Sec/Div", "Trigger Voltage", "Mean VPP Voltage"
            ],
            "Value": [
                f"{signal_freq} Hz", f"{signal_amp} V", f"{dc_bias} V",
                f"{v_scale} V/div", f"{v_offset} V", coupling,
                f"{t_scale} s/div", f"{trig_lvl} V", f"{mean_vpp} V"
            ]
        })

        st.markdown("##### 📊 Instrument Parameters")  
        st.dataframe(
        df_params,
        use_container_width=True,
        hide_index=True,   
        height=352         
        )
        with st.popover("📖 SCPI Cheat Sheet (Oscilloscope & Gen)", use_container_width=True):
            st.caption("Tip: Add '?' after set commands (e.g., :FREQuency?) to query current values.")
            
            st.markdown("**〰️ Signal Generator**")
            st.code(
                "*IDN?                        # Query device identity\n"
                "*RST                         # Reset to default settings\n"
                ":FREQuency 500               # Set frequency in Hz (or :FREQuency?)\n"
                ":VOLTage 2.0                 # Set amplitude Vpp in V (or :VOLTage?)\n"
                ":VOLTage:OFFSet 0.5          # Set DC offset in V (or :VOLTage:OFFSet?)\n"
                ":OUTPut ON                   # Enable output (ON / OFF)",
                language="bash"
            )
            
            st.markdown("**📈 Oscilloscope**")
            st.code(
                "*IDN?                        # Query device identity\n"
                ":RUN / :STOP / :SINGle       # Acquisition control\n"
                ":CHANnel1:DISPlay ON         # Toggle Channel 1 (ON / OFF)\n"
                ":CHANnel1:SCALe 1.0          # Vertical scale in V/div\n"
                ":CHANnel1:COUPling DC        # Input coupling: DC, AC, GND\n"
                ":TIMebase:MAIN:SCALe 0.002   # Horizontal timebase in s/div\n"
                ":TIMebase:MAIN:OFFSet 0.0    # Horizontal delay/offset in s\n"
                ":TRIGger:EDGe:LEVel 0.5      # Trigger level in V\n"
                ":MEASure:AVERage? VPP,CHANnel1   # Measure Peak-to-Peak voltage\n"
                ":MEASure:AVERage? FREQ,CHANnel1  # Measure signal frequency",
                language="bash"
            )


    if select_device in ["Multimeter", "DC power supply"]:
        mul_dev = st.session_state["mul"]
        psu_dev = st.session_state["psu"]

        auto_range = mul_dev.query(":VOLTage:DC:RANGe:AUTO?").strip()
        range_value = float(mul_dev.query(":VOLTage:DC:RANGe?"))
        voltage_mode = mul_dev.query(":CONFigure?").strip()
        output_voltage = float(psu_dev.query(":VOLTage?"))
        current_protect = float(psu_dev.query(":CURRent?"))
        actural_voltage = float(psu_dev.query(":MEASure:VOLTage?"))
        actural_current = float(psu_dev.query(":MEASure:CURRent?"))

        #data = {
                #"Multimeter Auto Measure": auto_range,
                #"Measure Range": range_value, 
                #"Voltage Mode": voltage_mode,
                #"DC Power Output Voltage": output_voltage,
                #"Current Protection Value": current_protect,
                #"Actural Current Output": actural_current,
                #"Actural Voltage Output": actural_voltage
                #}
        
        #with st.container(border=True):


            #for i, (key, value) in enumerate(data.items()):
                #col1, col2 = st.columns([1, 2])
                #with col1:
                    #st.markdown(f"**{key}**")  
                #with col2:
                    #st.markdown(f"{value}")  

                #if i < len(data) - 1:
                    #st.divider()
        df_params = pd.DataFrame({
                    "Parameter": [
                        "Multimeter Auto Measure", "Measure Range", "Voltage Mode",
                        "DC Power Output Voltage", "Current Protection Value","Actural Current Output",
                        "Actural Voltage Output"
                    ],
                    "Value": [
                        auto_range, f"{range_value} V", voltage_mode,
                        f"{output_voltage} V", f"{current_protect} A", 
                        f"{actural_current} A", f"{actural_voltage} V", 
                    ]
                })
        
        st.markdown("##### 📊 Instrument Parameters")  
        st.dataframe(
        df_params,
        use_container_width=True,
        hide_index=True,   
        height=352         
        )
        with st.popover("📖 SCPI Cheat Sheet (DMM & Power)", use_container_width=True):
            st.caption("Click the copy icon on the right of any block to copy:")
            
            st.markdown("**📟 Multimeter (DMM)**")
            st.code(
                ":MEASure:VOLTage:DC?   # Measure DC voltage (V)\n"
                ":MEASure:VOLTage:AC?   # Measure AC voltage (V)\n"
                ":MEASure:CURRent:DC?   # Measure DC current (A)\n"
                ":MEASure:RESistance?   # Measure 2-wire resistance (Ω)\n"
                ":CONFigure:VOLTage:DC  # Set mode to DC voltage\n"
                ":CONFigure:VOLTage:AC  # Set mode to AC voltage\n"
                ":CONFigure:CURRent:DC  # Set mode to DC current\n"
                ":CONFigure:RESistance  # Set mode to Resistance",
                language = "bash"
            )
            
            st.markdown("**🔋 DC Power Supply**")
            st.code(
                ":VOLTage 5.0           # Set target voltage (V)\n"
                ":CURRent 1.0           # Set current limit (A)\n"
                ":OUTPut ON             # Turn output ON (or OFF)\n"
                ":MEASure:VOLTage?      # Query actual output voltage\n"
                ":MEASure:CURRent?      # Query actual output current",
                language = "bash"
            )