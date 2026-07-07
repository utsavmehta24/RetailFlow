# `hadoop/` — Windows PySpark Compatibility Layer

PySpark runs on the JVM and internally uses the [Apache Hadoop](https://hadoop.apache.org/) filesystem API to read and write data — even when running entirely on a single local machine. On Linux and macOS, PySpark ships with everything it needs. On **Windows**, it requires two native DLL/EXE files that are not bundled in the standard PySpark distribution.

This folder provides those files so that PySpark works cleanly on Windows without any system-wide Hadoop installation.

---

## Folder structure

```
hadoop/
└── bin/
    ├── winutils.exe   ← Hadoop POSIX compatibility shim for Windows
    └── hadoop.dll     ← Native Windows DLL required by the JVM Hadoop layer
```

---

## What each file does

### `winutils.exe`

On Linux, Hadoop calls standard POSIX system calls (`chmod`, `chown`, `stat`, etc.) to manage file permissions on the local filesystem. Windows does not have these system calls.

`winutils.exe` is a small Windows-native executable that **re-implements those POSIX calls** using the Windows API. Without it, PySpark throws a fatal error on startup:

```
ERROR Shell: Failed to locate the winutils binary in the hadoop binary path
java.io.IOException: Could not locate executable null\bin\winutils.exe in the Hadoop binaries.
```

### `hadoop.dll`

This is the native Windows DLL that the JVM Hadoop layer loads at startup. It provides low-level filesystem and IO functions. Without it, even if `winutils.exe` is present, PySpark will crash with:

```
Unable to load native-hadoop library for your platform
```

---

## How the project uses these files

`scripts/run_pipeline.ps1` sets the `HADOOP_HOME` environment variable to this folder at runtime before launching any PySpark job:

```powershell
$env:HADOOP_HOME = "<project_root>\hadoop"
$env:Path = "$env:HADOOP_HOME\bin;" + $env:Path
```

This tells the JVM exactly where to find `winutils.exe` and `hadoop.dll` — no system-wide installation required.

---

## Auto-download on first run

On a fresh clone these files will be absent. `run_pipeline.ps1` detects this and **automatically downloads** them from the community-maintained repository:

```
https://github.com/cdarlint/winutils
```

The script fetches the Hadoop 3.2.1 builds which are compatible with PySpark 3.5.x's bundled Hadoop libraries.

You do **not** need to download anything manually — just run `setup.ps1` followed by `run_pipeline.ps1` and the binaries will appear here automatically.

---

## Is this needed on Linux or macOS?

No. This folder is **Windows-only**. On Linux and macOS, PySpark uses the native POSIX filesystem layer directly and does not need `winutils.exe` or `hadoop.dll`. The pipeline scripts detect the OS and skip this step on non-Windows platforms.

---

## What this folder does NOT contain

- It does not contain a full Hadoop installation (no HDFS, no YARN, no MapReduce).
- It does not contain the Hadoop JAR files (PySpark fetches those via Maven at runtime).
- It does not configure a Hadoop cluster — the pipeline runs entirely in local PySpark standalone mode.

---

## Reference

- [winutils source + binaries](https://github.com/cdarlint/winutils) — community-maintained Windows Hadoop binaries
- [PySpark on Windows guide](https://spark.apache.org/docs/latest/api/python/getting_started/install.html)
- [Apache Hadoop](https://hadoop.apache.org/)

---

*Back to [project root](../Readme.md)*
