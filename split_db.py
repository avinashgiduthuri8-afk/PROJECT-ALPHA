import os

file_path = 'vps_alpha_v2.db'
chunk_size = 50 * 1024 * 1024 # 50 MB

with open(file_path, 'rb') as f:
    chunk = f.read(chunk_size)
    part_num = 1
    while chunk:
        with open(f'{file_path}.part{part_num}', 'wb') as chunk_file:
            chunk_file.write(chunk)
        part_num += 1
        chunk = f.read(chunk_size)
        
print("Split complete")
