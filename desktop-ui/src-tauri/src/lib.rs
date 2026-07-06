use std::{
    io,
    net::TcpStream,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::Duration,
};

use tauri::{Manager, RunEvent};

struct BackendProcess(Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            if !backend_is_running() {
                let backend_script = backend_script_path(app.handle())?;
                let reports_dir = reports_dir(app.handle())?;
                std::fs::create_dir_all(&reports_dir)?;

                let child = Command::new("python3")
                    .arg(&backend_script)
                    .arg("8787")
                    .env("REPO_SCANNER_REPORT_ROOT", reports_dir)
                    .current_dir(
                        backend_script
                            .parent()
                            .map(PathBuf::from)
                            .unwrap_or_else(|| PathBuf::from(".")),
                    )
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .spawn()
                    .map_err(|err| {
                        std::io::Error::new(
                            std::io::ErrorKind::Other,
                            format!(
                                "Unable to start local scanner backend at {}: {err}",
                                backend_script.display()
                            ),
                        )
                    })?;

                *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);
                wait_for_backend();
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                stop_backend(window.app_handle());
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                stop_backend(app_handle);
            }
        });
}

fn backend_is_running() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:8787".parse().expect("valid backend socket address"),
        Duration::from_millis(250),
    )
    .is_ok()
}

fn wait_for_backend() {
    for _ in 0..30 {
        if backend_is_running() {
            return;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
}

fn stop_backend(app_handle: &tauri::AppHandle) {
    let state = app_handle.state::<BackendProcess>();
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    };
}

fn backend_script_path(app_handle: &tauri::AppHandle) -> io::Result<PathBuf> {
    let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|path| path.parent())
        .map(|path| path.join("web_app.py"));
    if let Some(path) = dev_path {
        if path.exists() {
            return Ok(path);
        }
    }

    Ok(app_handle
        .path()
        .resource_dir()
        .map_err(io_other)?
        .join("backend")
        .join("web_app.py"))
}

fn reports_dir(app_handle: &tauri::AppHandle) -> io::Result<PathBuf> {
    if cfg!(debug_assertions) {
        return Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|path| path.parent())
            .map(|path| path.join("gitleaks-web-reports"))
            .unwrap_or_else(|| PathBuf::from("gitleaks-web-reports")));
    }

    Ok(app_handle
        .path()
        .app_data_dir()
        .map_err(io_other)?
        .join("gitleaks-web-reports"))
}

fn io_other(error: impl std::fmt::Display) -> io::Error {
    io::Error::new(io::ErrorKind::Other, error.to_string())
}
