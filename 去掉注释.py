import tokenize
import io
import os

def remove_comments_from_python_code(code_string):
    """
    Removes comments from a Python code string using the tokenize module.
    """
    result_tokens = []
    code_io = io.StringIO(code_string)                                                        

    try:
        for token_info in tokenize.generate_tokens(code_io.readline):
                                                                         
            if token_info.type != tokenize.COMMENT:
                result_tokens.append(token_info)
    except tokenize.TokenError as e:
        print(f"Tokenization error: {e} - original content will be kept for this part.")
                                                                               
                                                                                      
                                                                                       
        return code_string                                                  
    except Exception as e:
        print(f"An unexpected error occurred during tokenization: {e}")
        return code_string           

    try:
        return tokenize.untokenize(result_tokens)
    except Exception as e:
        print(f"Error during untokenization: {e} - original content will be kept.")
        return code_string                               

def process_py_file(file_path, overwrite=True, backup_ext=".bak"):
    """
    Processes a single .py file: reads it, removes comments, and writes it back.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_code = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return

    cleaned_code = remove_comments_from_python_code(original_code)

                                                                                       
    if cleaned_code != original_code and cleaned_code.strip():
        try:
            if overwrite:
                                           
                if backup_ext:
                    backup_file_path = file_path + backup_ext
                    with open(backup_file_path, 'w', encoding='utf-8') as bf:
                        bf.write(original_code)
                    print(f"Backup created: {backup_file_path}")

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_code)
                print(f"Processed and updated: {file_path}")
            else:
                                                                     
                new_file_path = file_path.replace(".py", "_no_comments.py")
                with open(new_file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_code)
                print(f"Processed and saved to: {new_file_path}")
        except Exception as e:
            print(f"Error writing file {file_path} (or its new version): {e}")
    elif cleaned_code == original_code:
        print(f"No comments to remove or no change in: {file_path}")
    else:
        print(f"Skipping empty or problematic cleaned code for: {file_path}")


def batch_process_py_files(root_dir=".", overwrite_files=True, create_backup=True):
    """
    Walks through the root_dir and its subdirectories,
    processing all .py files.
    """
    backup_extension = ".bak" if create_backup and overwrite_files else None

    for dirpath, dirnames, filenames in os.walk(root_dir):
                                                                                             
                                                                                         

        for filename in filenames:
            if filename.endswith(".py"):
                file_path = os.path.join(dirpath, filename)
                print(f"Found Python file: {file_path}")
                process_py_file(file_path, overwrite=overwrite_files, backup_ext=backup_extension)

if __name__ == "__main__":
                           
    target_directory = "."                                                              
                                                                                          

                                           
                                                                     
    OVERWRITE_ORIGINAL_FILES = True              

                                                                                 
    CREATE_BACKUPS = True

                               

    if OVERWRITE_ORIGINAL_FILES:
        print("WARNING: This script will modify .py files in place.")
        if CREATE_BACKUPS:
            print("Backup files with .bak extension will be created.")
        else:
            print("NO backup files will be created.")
        confirm = input(f"Are you sure you want to proceed with processing directory '{os.path.abspath(target_directory)}'? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Operation cancelled by user.")
            exit()

    print(f"\nStarting batch processing in: {os.path.abspath(target_directory)}\n")
    batch_process_py_files(target_directory,
                           overwrite_files=OVERWRITE_ORIGINAL_FILES,
                           create_backup=CREATE_BACKUPS)
    print("\nBatch processing finished.")