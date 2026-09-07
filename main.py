import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import piexif
import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()


HEIC_EXTS = {".heic", ".heif"}

def list_heic_files(folder: Path) -> list[Path]:
    files = []
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in HEIC_EXTS:
            files.append(path)
    return sorted(files)

def convert_heic_to_jpeg(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as image:
        exif_bytes = image.info.get("exif")
        rgb = image.convert("RGB")
        
        if not exif_bytes:
            rgb.save(dest, format="JPEG", quality=95)
            return "ok_no_exif"
        
        try:
            exif_dict = piexif.load(exif_bytes)
            exif_dict["thumbnail"] = None
            new_exif = piexif.dump(exif_dict)
            rgb.save(dest, format="JPEG", quality=95, exif=new_exif)
            return "ok"
        except Exception:
            rgb.save(dest, format="JPEG", quality=95)
            return "ok_no_exif"
 
def append_log(message: str):
    log_text.insert(tk.END, message + "\n")
    log_text.see(tk.END) 

def choose_folder():
    folder = filedialog.askdirectory(title = "HEICが入ったフォルダを選択")
    if not folder:
        return
    
    folder_var.set(folder)
    files = list_heic_files(Path(folder))
    count_label.config(text = f"対象：{len(files)} 件")
    
    log_text.delete("1.0", tk.END)
    if not files: 
        append_log("対象ファイルがありません")
        return
    
    for path in files:
        append_log(path.name)


def open_jpeg_folder():
    folder = folder_var.get()
    if folder == "フォルダが選ばれていません":
        messagebox.showwarning("確認", "フォルダを選択してください")
        return

    jpeg_dir = Path(folder) / "jpeg"
    if not jpeg_dir.is_dir():
        messagebox.showwarning(
            "確認", "jpegフォルダがまだありません。先に変換してください。"
        )
        return

    os.startfile(jpeg_dir)


def set_buttons_enabled(enabled: bool):
    state = "normal" if enabled else "disabled"
    browse_button.config(state = state)
    convert_button.config(state = state)
        
def start_convert():
    folder = folder_var.get()
    if folder == "フォルダが選ばれていません":
        messagebox.showwarning("確認", "フォルダを選択してください")
        return
    files = list_heic_files(Path(folder))
    if not files:
        messagebox.showwarning("確認", "対象ファイルがありません")
        return
    
    log_text.delete("1.0", tk.END)
    set_buttons_enabled(False)
    
    thread = threading.Thread(
        target = convert_worker,
        args = (Path(folder), files),
        daemon=True
        )
    thread.start()


def convert_worker(folder: Path, files: list[Path]):
    output_dir = Path(folder)/"jpeg"
    output_dir.mkdir(parents = True, exist_ok = True)
    
    success = 0
    failed = 0
    total = len(files)
    
    for i, src in enumerate(files, start=1):
        dest = output_dir / (src.stem + ".jpg")
        msg_queue.put({"type": "progress", "done": i, "total": total})
        try:
            result = convert_heic_to_jpeg(src, dest)
            success += 1
            msg_queue.put({"type": "log", "text": f"{src.name} → {dest}"})
            if result == "ok_no_exif":
                msg_queue.put(
                    {"type": "log", "text": "  （メタデータなしで保存しました）"}
                )
        except Exception as e:
            failed += 1
            msg_queue.put({"type": "log", "text": f"{src.name} → 失敗: {e}"})
        msg_queue.put(
            {"type": "result", "success": success, "failed": failed}
        )
    msg_queue.put(
        {
            "type": "done",
            "success": success,
            "failed": failed,
        }
    )


def poll_queue():
    while True:
        try:
            msg = msg_queue.get_nowait()
        except queue.Empty:
            break
        kind = msg["type"]
        if kind == "progress":
            progress_label.config(text=f"進捗: {msg['done']} / {msg['total']}")
        elif kind == "log":
            append_log(msg["text"])
        elif kind == "result":
            result_label.config(
                text=f"成功 {msg['success']} / 失敗 {msg['failed']}"
            )
        elif kind == "done":
            append_log(f"完了: 成功 {msg['success']} / 失敗 {msg['failed']}")
            set_buttons_enabled(True)
    root.after(100, poll_queue)
    
    
    
root = tk.Tk()
msg_queue = queue.Queue()
root.title("HEIC to JPEG 変換")
root.geometry("640x420")
root.minsize(520, 360)

folder_var = tk.StringVar(value="フォルダが選ばれていません")

main = tk.Frame(root, padx=12, pady=12)
main.pack(fill="both", expand=True)
main.columnconfigure(1, weight=1)
main.rowconfigure(4, weight=1)

BUTTON_WIDTH = 12

tk.Label(main, text="フォルダ:").grid(row=0, column=0, sticky="w", pady=4)
tk.Label(main, textvariable=folder_var, anchor="w").grid(
    row=0, column=1, sticky="ew", padx=8, pady=4
)
browse_button = tk.Button(
    main, text="参照", width=BUTTON_WIDTH, command=choose_folder
)
browse_button.grid(row=0, column=2, sticky="e", pady=4)

count_label = tk.Label(main, text="対象: - 件")
count_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
convert_button = tk.Button(
    main, text="変換開始", width=BUTTON_WIDTH, command=start_convert
)
convert_button.grid(row=1, column=2, sticky="e", pady=4)

progress_label = tk.Label(main, text="進捗: -")
progress_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
open_button = tk.Button(
    main, text="jpegを開く", width=BUTTON_WIDTH, command=open_jpeg_folder
)
open_button.grid(row=2, column=2, sticky="e", pady=4)

result_label = tk.Label(main, text="成功 - / 失敗 -")
result_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)

log_text = tk.Text(main, height=12)
log_text.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(8, 0))

poll_queue()
root.mainloop()
