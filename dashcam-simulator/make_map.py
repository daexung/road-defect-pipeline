import json
import folium

points = []
with open(r'C:\Users\daeseong\Desktop\pothall-pjt\fake_log_gen_output.jsonl') as f:
    for line in f:
        d = json.loads(line)
        if d['cp_class_name'] in ('P','U_P'):
            points.append(d)

m = folium.Map(location=[37.4968, 126.9003], zoom_start=13)

for p in points:
    is_P = p['cp_class_name'] == 'P'
    color = 'red' if is_P else 'orange'
    radius = 8 if is_P else 4
    folium.CircleMarker(
        location=[p['gps_lat'], p['gps_lng']],
        radius=radius,
        color='blue' if p['direction'] == 'forward' else 'green',
        fill=True,
        fill_color=color,
        fill_opacity=0.8,
        popup=f"{p['cp_class_name']} | conf: {p['confidence']} | {p['timestamp'][11:19]}"
    ).add_to(m)

m.save(r'C:\Users\daeseong\Desktop\pothall-pjt\pothole_map.html')
print("저장 완료")