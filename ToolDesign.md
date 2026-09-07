# HEIC → JPEG 変換ツール 設計概要

勉強用に、自分で実装するための設計メモです。まずは動く最小構成（MVP）を作り、そのあと必要に応じて拡張します。

## 1. 目的

指定したフォルダ内の HEIC / HEIF 画像をまとめて JPEG に変換する。  
iPhone などで撮影した写真の **撮影日時** と **GPS（緯度・経度・高度）** は、変換後の JPEG にも残す。

## 2. 技術選定

| 役割 | 採用 | 理由 |
|------|------|------|
| 言語 | Python 3.11 以上 | 画像処理と GUI を短く書ける |
| GUI | tkinter（標準ライブラリ） | フォルダ選択が簡単。追加インストール不要 |
| HEIC 読み込み | pillow-heif | Pillow から HEIC を開ける |
| 画像変換 | Pillow (PIL) | JPEG 保存が標準的 |
| EXIF コピー | piexif | 撮影日・GPS を JPEG に書き戻せる |

Electron や C# よりセットアップが軽く、学習コストも低い構成です。

## 3. 機能一覧

### 3.1 MVP（最初に作る範囲）

- フォルダを選択する
- 選択フォルダ直下の `.heic` / `.heif`（大文字小文字は問わない）を列挙する
- 各ファイルを JPEG（`.jpg`）に変換する
- 出力先は、選択フォルダ内の `jpeg` サブフォルダ（なければ作成）
- 同名の JPEG が既にある場合は上書きしない（`IMG_0001_1.jpg` のように連番を付ける）
- 次のメタデータを残す
  - 撮影日時（`DateTimeOriginal` など）
  - 緯度・経度・高度（GPS IFD）
  - 可能なら向き（`Orientation`）
- 進捗（何件中何件）と成功 / 失敗件数を画面に出す
- 失敗したファイルは理由をログ表示する（壊れたファイルがあっても処理は止めない）

### 3.2 今回やらないこと（後回し）

- サブフォルダ再帰変換
- 画質スライダー、リサイズ
- ドラッグ＆ドロップ
- `.exe` 化（PyInstaller）
- 変換前プレビュー

必要になったら「8. 拡張案」を見て足します。

## 4. 画面のイメージ

ウィンドウは 1 枚で十分です。

```
┌─────────────────────────────────────────┐
│  HEIC → JPEG 変換                       │
│                                         │
│  フォルダ: [ C:\Photos\iPhone ] [参照]  │
│                                         │
│  対象: 12 件                             │
│                                         │
│  [変換開始]                              │
│                                         │
│  進捗: 3 / 12                            │
│  成功 3 / 失敗 0                         │
│                                         │
│  ログ:                                   │
│  IMG_0001.HEIC → jpeg\IMG_0001.jpg      │
│  IMG_0002.HEIC → 失敗: EXIF が読めない   │
└─────────────────────────────────────────┘
```

操作の流れ:

1. 「参照」でフォルダを選ぶ（`filedialog.askdirectory`）
2. 対象件数を表示する
3. 「変換開始」で一括変換する
4. ログと件数を更新する

変換中はボタンを無効化し、終わったら戻します。  
GUI が固まらないよう、変換は **バックグラウンドスレッド** で行い、画面更新だけメインスレッドに戻します（`after` や `queue`）。

## 5. 推奨ディレクトリ構成

```
HeicToJpeg/
├── ToolDesign.md          # この設計書
├── requirements.txt
├── README.md              # 使い方（実装後でよい）
├── main.py                # 起動入口。GUI を開く
├── ui.py                  # tkinter の画面
├── converter.py           # HEIC → JPEG 変換とメタデータ
└── file_utils.py          # 対象ファイル列挙、出力パス決定
```

学習しやすいように、画面・変換・ファイル処理を分けます。  
最初は `main.py` 1 ファイルでも構いません。動いたら上記のように分割すると追いやすくなります。

## 6. モジュールの役割

### `file_utils.py`

- `list_heic_files(folder: Path) -> list[Path]`
  - 拡張子が `.heic` / `.heif` のファイルだけ返す
  - Windows なので大文字小文字は無視する（`suffix.lower()`）
- `make_output_path(src: Path, output_dir: Path) -> Path`
  - `IMG_0001.HEIC` → `jpeg/IMG_0001.jpg`
  - 既存ファイルと衝突したら `IMG_0001_1.jpg`, `IMG_0001_2.jpg` ...
- `ensure_output_dir(folder: Path) -> Path`
  - `{folder}/jpeg` を作って返す

### `converter.py`

中心ロジックです。1 ファイル変換を関数 1 つにします。

```text
convert_heic_to_jpeg(src: Path, dest: Path) -> None
```

処理手順:

1. `pillow_heif.register_heif_opener()` を起動時に 1 回呼ぶ
2. `Image.open(src)` で HEIC を開く
3. EXIF バイト列を取る（`image.info.get("exif")`）
4. RGB に変換する（JPEG は RGBA をそのまま保存できない）
   - `image.convert("RGB")`
5. JPEG として保存する
   - 品質はまずは `quality=95` 固定でよい
   - `exif=` に piexif で整えたバイトを渡す
6. EXIF が取れない場合でも画像変換は成功扱いにする（ログに「メタデータなし」と出す）

### `ui.py` / `main.py`

- フォルダ選択、件数表示、変換開始、ログ出力
- 変換ループはワーカースレッド
- 1 件終わるたびにキュー経由でログを足す

## 7. メタデータを残す実装方針

Pillow の `save()` だけだと EXIF が落ちることがあります。  
**読み取った EXIF を piexif で載せ直す**のが安全です。

残したい項目（代表例）:

| 意味 | EXIF タグ |
|------|-----------|
| 撮影日時 | `0th` / `Exif` の `DateTime`, `DateTimeOriginal`, `DateTimeDigitized` |
| 緯度 | `GPS` の `GPSLatitude`, `GPSLatitudeRef` |
| 経度 | `GPS` の `GPSLongitude`, `GPSLongitudeRef` |
| 高度 | `GPS` の `GPSAltitude`, `GPSAltitudeRef` |
| 向き | `0th` の `Orientation` |

実装の目安:

1. HEIC から `exif` バイトを取得する
2. `piexif.load(exif_bytes)` で辞書にする
3. 不要ならサムネイル（`thumbnail`）は捨ててもよい（ファイルサイズ節約）
4. JPEG 向けに問題になるタグがあれば除去する
   - 例: `1st` IFD や、JPEG で不正になりやすい一部タグ
5. `piexif.dump(exif_dict)` して `image.save(..., format="JPEG", quality=95, exif=exif_bytes)` する

検証方法（実装後）:

- Windows のプロパティ → 詳細、または
- `exiftool` で変換前後を比較する

確認するとよいキー:

- `DateTimeOriginal`
- `GPSLatitude` / `GPSLongitude` / `GPSAltitude`

GPS が元ファイルに無い写真（屋内など）は、変換後も GPS が無いのが正しい動きです。

## 8. 変換時の注意点

- **色空間**: HEIC は RGBA や特殊モードのことがある。保存前に必ず `RGB` にする
- **Orientation**: EXIF の向きを残すか、画像を回転してから Orientation を 1 にするか、どちらかに統一する。MVP は「EXIF をそのままコピー」でよい
- **Live Photos**: `.HEIC` と対になる `.MOV` は変換対象にしない
- **ファイルロック**: 開いているファイルは `with Image.open(...)` で閉じる
- **パス**: `pathlib.Path` を使う。日本語フォルダ名も想定する
- **拡張子**: `.HEIC` / `.heic` / `.HEIF` / `.heif` を対象にする。`.jpg` や `.png` は無視する

## 9. エラー処理

1 ファイルの失敗で全体を止めない。

| 状況 | 扱い |
|------|------|
| フォルダ未選択 | 変換開始不可。メッセージを出す |
| HEIC が 0 件 | 「対象ファイルがありません」 |
| 読めない / 壊れている | その件を失敗にして次へ |
| 書き込み権限なし | 失敗ログ。出力フォルダ作成失敗なら全体中止でよい |
| EXIF なし / 壊れている | 画像だけ保存し、警告ログ |

例外は `except Exception as e` で握りつぶさず、ファイル名と `e` をログに出します。

## 10. 依存パッケージ

`requirements.txt` の例:

```
pillow>=10.0.0
pillow-heif>=0.16.0
piexif>=1.1.3
```

セットアップ:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

`pillow-heif` は内部で libheif を使います。Windows では pip だけで入ることが多いです。インストールに失敗したら、Python のビット数（64bit）とバージョンを確認します。

## 11. 実装する順番（学習用）

この順だと、途中で動作確認しやすいです。

1. **空の tkinter 窓**を出す（`main.py`）
2. **フォルダ選択**と、選択パスの表示
3. **HEIC 一覧**をログに出す（まだ変換しない）
4. **1 ファイル変換**（メタデータなしでよい）。`jpeg` フォルダに保存されることを確認
5. **piexif で EXIF コピー**を足す。プロパティで撮影日・GPS を確認
6. **複数ファイルのループ**と成功 / 失敗カウント
7. **スレッド化**して、変換中に画面が固まらないようにする
8. **上書き回避**と細かいエラーメッセージ

## 12. 主な関数の契約（実装時の目安）

```python
def list_heic_files(folder: Path) -> list[Path]:
    """folder 直下の HEIC/HEIF を名前順で返す。"""

def unique_jpeg_path(output_dir: Path, stem: str) -> Path:
    """output_dir / f'{stem}.jpg'。存在すれば stem_1, stem_2..."""

def extract_exif(image: Image.Image) -> bytes | None:
    """Pillow 画像から EXIF バイトを取り出す。無ければ None。"""

def sanitize_exif(exif_bytes: bytes) -> bytes:
    """piexif で読み、JPEG に載せられる形へ整えて dump する。"""

def convert_heic_to_jpeg(src: Path, dest: Path) -> str:
    """
    変換する。
    戻り値: 'ok' / 'ok_no_exif' など。失敗は例外を投げる。
    """
```

GUI 側はこれらの関数を呼ぶだけにすると、変換ロジックを単体で試しやすくなります。

## 13. 動作確認チェックリスト

実装後、実機の HEIC（iPhone 写真が望ましい）で次を確認します。

- [ ] フォルダを選ぶと件数が正しい
- [ ] `.heic` と `.HEIC` の両方が対象になる
- [ ] `jpeg` フォルダに同名（拡張子だけ jpg）で出力される
- [ ] 既に同名 jpg があるとき、元ファイルを上書きしない
- [ ] 画像が開ける（色が極端に変でない）
- [ ] 撮影日時が残っている
- [ ] GPS 付き写真は緯度・経度・高度が残っている
- [ ] GPS なし写真はエラーにならない
- [ ] 壊したダミーファイルを混ぜても、他のファイルは変換される
- [ ] 変換中にウィンドウ操作ができる（固まらない）

## 14. 拡張案（余裕があれば）

- サブフォルダも再帰する（チェックボックス）
- 出力先を「同じフォルダ」か「jpeg サブフォルダ」か選ぶ
- JPEG 品質（80〜100）
- 変換済みをスキップ（同名 jpg があり、更新日時が新しいとき）
- ログを `convert_log.txt` に保存
- PyInstaller で exe 化

## 15. 学習時に見るとよいポイント

- `pathlib` でパスを扱う
- `tkinter.filedialog` とウィジェット配置（`pack` か `grid`）
- Pillow の `Image.open` / `convert` / `save`
- EXIF は「画像ピクセル」とは別データであること
- GUI スレッドと作業スレッドを分ける理由（応答性）

この設計どおりでなくても構いません。迷ったときの判断材料として使ってください。
