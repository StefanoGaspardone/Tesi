# Strings Compression Techniques

## Table of Contents

- [Overview](#overview)
- [How to Run Python Scripts](#how-to-run-python-scripts)
  - [1. Exhaustive Compression (`c2_exhaustive.py`)](#1-exhaustive-compression-c2_exhaustivepy)
  - [2. Restricted Exhaustive Search Compression (`c2_exhaustive_restricted.py`)](#2-restricted-exhaustive-search-compression-c2_exhaustive_restrictedpy)
  - [3. Standard & Native Algorithms](#3-standard--native-algorithms)
- [C Implementations (`c2_exhaustive_c` & `c2_exhaustive_restricted_c`)](#c-implementations-c2_exhaustive_c--c2_exhaustive_restricted_c)
  - [1. Build Instructions](#1-build-instructions)
  - [2. How to Run C Executables](#2-how-to-run-c-executables)
- [Contributors](#contributors)

---

## Overview

This repository contains the source code and experimental framework for a thesis project focusing on compression algorithms, customs (such as `c2_exhaustive` and `c2_exhaustive_restricted`), and standard compression algorithms (such as Brotli, Zlib, and Zstandard).

The project structure is organized as follows:

- **`inputs/`**: Contains raw text files used as inputs (e.g., `ap.txt`, `colonnina.txt`, `wifi.txt`).
- **`logs/`**: Stores execution logs.
- **`outputs/`**: Stores generated output files and compressed data.
- **`src/`**: Contains core Python scripts implementing compression algorithms and helper modules.

---

## How to Run Python Scripts

Navigate to the `src/` directory before executing the scripts:

```bash
cd src
```

> **Note on File Paths:**
> - When running in **`compress`** mode, the input file is expected to be located inside the `inputs/` folder.
> - When running in **`decompress`** mode, the input file (the compressed binary) is expected to be located inside the `outputs/` folder.

---

### 1. Exhaustive Compression (`c2_exhaustive.py`)

Performs compression and decompression using an exhaustive search strategy (DFS) with Branch & Bound.

#### Compress

```bash
python c2_exhaustive.py compress <input_file_name> [output_file_name] [options]
```

Example:

```bash
python c2_exhaustive.py compress ap.txt ap_exhaustive.bin --encoding huffman-len
```

#### Decompress

```bash
python c2_exhaustive.py decompress <input_file_name> [output_file_name]
```

Example:

```bash
python c2_exhaustive.py decompress ap_exhaustive.bin ap_decompressed.txt
```

#### CLI Options

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `mode` | `str` | *Required* | Operation mode: `compress` or `decompress`. |
| `input` | `str` | *Required* | Name/path of the input file (`inputs/` for compress, `outputs/` for decompress). |
| `output` | `str` | `None` | Name/path of the output file (optional). If not provided, a default name will be used. During decompression, if not provided, the decompressed output will be written in the console. |
| `--min-len` | `int` | `3` | Minimum match length. |
| `--max-len` | `int` | `32` | Maximum match length. |
| `--max-dict` | `int` | `1023` | Maximum dictionary size. |
| `--exh-max-depth` | `int` | `0` | DFS depth: `0` = greedy, `-1` = no depth limit, `N` = depth N. |
| `--encoding` | `str` | `fixed` | Symbol encoding mode. Choices: `fixed`, `huffman-freq`, `huffman-len`, `positional`. |

---

### 2. Restricted Exhaustive Search Compression (`c2_exhaustive_restricted.py`)

Performs compression and decompression using a restricted lookahead exhaustive search strategy.

#### Compress

```bash
python c2_exhaustive_restricted.py compress <input_file_name> [output_file_name] [options]
```

Example:

```bash
python c2_exhaustive_restricted.py compress ap.txt ap_restricted.bin --lookahead-depth 2 --lookahead-topk 3
```

#### Decompress

```bash
python c2_exhaustive_restricted.py decompress <input_file_name> [output_file_name]
```

Example:

```bash
python c2_exhaustive_restricted.py decompress ap_restricted.bin ap_decompressed.txt
```

#### CLI Options

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `mode` | `str` | *Required* | Operation mode: `compress` or `decompress`. |
| `input` | `str` | *Required* | Name/path of the input file (`inputs/` for compress, `outputs/` for decompress). |
| `output` | `str` | `None` | Name/path of the output file (optional). If not provided, a default name will be used. During decompression, if not provided, the decompressed output will be written in the console. |
| `--min-len` | `int` | `3` | Minimum match length. |
| `--max-len` | `int` | `32` | Maximum match length. |
| `--max-dict` | `int` | `1023` | Maximum dictionary size. |
| `--lookahead-depth` | `int` | `0` | Lookahead search depth (`0` = greedy). |
| `--lookahead-topk` | `int` | `1` | Candidates evaluated per node (`1` = greedy). |
| `--encoding` | `str` | `fixed` | Symbol encoding mode. Choices: `fixed`, `huffman-freq`, `huffman-len`, `positional`. |

---

### 3. Standard & Native Algorithms

The repository includes implementations for standard and native compression algorithms:

- **Zlib**: `zlib.py`, `zlib_native.py`
- **Zstandard**: `zstd.py`, `zstd_native.py`
- **Brotli**: `brotli_alg.py`, `brotli_native.py`

#### Compress

```bash
python <script_name>.py compress <input_file_name> [output_file_name]
```

Example:

```bash
python zlib_native.py compress ap.txt ap_zlib.bin
```

#### Decompress

```bash
python <script_name>.py decompress <input_file_name> [output_file_name]
```

Example:

```bash
python zlib_native.py decompress ap_zlib.bin ap_decompressed.txt
```

#### CLI Options

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `mode` | `str` | *Required* | Operation mode: `compress` or `decompress`. |
| `input` | `str` | *Required* | Name/path of the input file (`inputs/` for compress, `outputs/` for decompress). |
| `output` | `str` | `None` | Name/path of the output file (optional). If not provided, a default name will be used. During decompression, if not provided, the decompressed output will be written in the console. |

---

## C Implementations (`c2_exhaustive_c` & `c2_exhaustive_restricted_c`)

### 1. Build Instructions

Before running the C executables, navigate to their respective subdirectories inside `src/` and build the project using CMake:

```bash
cd src/<c_project_folder>
cmake --workflow --preset release (release-windows on Windows)
```

*Replace `<c_project_folder>` with either `c2_exhaustive_c` or `c2_exhaustive_restricted_c`.*

### 2. How to Run C Executables

Once built, the executables will be located in the build directory. The command-line options and parameters for the C binaries are **identical** to their Python counterparts (`c2_exhaustive.py` and `c2_exhaustive_restricted.py`).

#### Compress

```bash
./build/c2_exhaustive_c compress <input_file_name> [output_file_name] [options]
```

Example:

```bash
./build/c2_exhaustive_c compress ap.txt ap_exhaustive.bin --encoding huffman-len
```

#### Decompress

```bash
./build/c2_exhaustive_c decompress <input_file_name> [output_file_name]
```

Example:

```bash
./build/c2_exhaustive_c decompress ap_exhaustive.bin ap_decompressed.txt
```

---

## Contributors

- **[Stefano Gaspardone](https://github.com/StefanoGaspardone)** - Author
- **Stefano Scanzio** - Thesis Supervisor
- **Gianluca Cena** - Thesis Supervisor
