import sys
import os
import shutil

def move_files(file_path, output_dir):
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Open the file and read lines
    with open(file_path, 'r') as f:
        for line in f:
            # Extract the filename using string manipulation
            filename = line.strip().split("'")[1]
            
            # Check if the file exists
            if os.path.exists(filename):
                # Formulate the destination path
                dest_path = os.path.join(output_dir, os.path.basename(filename))
                # Move the file
                shutil.move(filename, dest_path)
            else:
                print(f"File {filename} not found.")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python script_name.py <file_path> <output_dir>")
        sys.exit(1)

    file_path = sys.argv[1]
    output_dir = sys.argv[2]

    move_files(file_path, output_dir)
