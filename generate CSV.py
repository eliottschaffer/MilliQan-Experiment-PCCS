import pandas as pd

high_byte = 0x85
fixed_middle = 0b110 << 3  # 0x30

rows = []
for high in range(4):      # bits 7:6
    for low in range(8):   # bits 2:0
        low_byte = (high << 6) | fixed_middle | low
        word = (high_byte << 8) | low_byte
        rows.append({'16-bit Word': f'0x{word:04X}'})

df = pd.DataFrame(rows)
df.to_excel('red_led_sweep.xlsx', index=False)
