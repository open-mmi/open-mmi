# Experimental CAN candidates — 2026-07-04

## Strong candidates

### Coolant temperature

CAN ID: 0x35B  
Signal: byte[3]  
Formula: coolant_temp_c = raw - 92

Evidence:
- Correlated against HVAC group 004.4 Coolant Temperature
- corr ≈ +0.950
- RMSE ≈ 0.40 °C
- raw range 171..178
- truth range 79..85 °C

Status:
- Strong candidate
- Needs cold-to-hot validation, ideally 40–90 °C

### Terminal 30 / battery voltage

CAN ID: 0x571  
Signal: byte[0]  
Tentative formula: voltage_v ≈ raw * 0.05 + 5.1

Evidence:
- Correlated against HVAC group 007.4 Voltage Terminal 30
- split capture 1: corr ≈ +0.814, RMSE ≈ 0.09 V, raw 127..134
- split capture 2: corr ≈ +0.811, RMSE ≈ 0.12 V, raw 171..176

Status:
- Strong byte-location candidate
- Formula needs one continuous validation capture

## Rejected / not enough evidence

RPM:
- No convincing passive infotainment CAN candidate found
- best brute-force candidates only corr ≈ 0.54–0.58, RMSE ≈ 334–347 rpm
- do not add to runtime profile yet

Heater flaps:
- No convincing passive candidate found in current capture
- keep diagnostic-only for now
