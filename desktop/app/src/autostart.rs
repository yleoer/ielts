//! Windows login startup, scoped to the current user.

/// Login startup passes this flag so the app starts in the tray without showing its window.
pub const LAUNCH_ARG: &str = "--autostart";

#[cfg(windows)]
mod platform {
    use std::io;
    use std::path::Path;
    use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE};
    use winreg::RegKey;

    const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
    const APPROVED: &str =
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run";
    const NAME: &str = "Cijian";

    fn optional<T>(result: io::Result<T>) -> io::Result<Option<T>> {
        match result {
            Ok(value) => Ok(Some(value)),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error),
        }
    }

    fn registered(key: &RegKey) -> io::Result<bool> {
        Ok(optional(key.get_value::<String, _>(NAME))?.is_some())
    }

    fn command(executable: &Path) -> String {
        // Windows Run commands must quote the full executable path.
        format!("\"{}\" {}", executable.display(), super::LAUNCH_ARG)
    }

    fn write_entry(key: &RegKey, executable: Option<&Path>) -> io::Result<()> {
        if let Some(executable) = executable {
            key.set_value(NAME, &command(executable))
        } else {
            optional(key.delete_value(NAME)).map(|_| ())
        }
    }

    /// Earlier versions registered the bare path, which opens the window at login.
    /// Only this executable's entry is rewritten, so a development build leaves it alone.
    fn upgrade_entry(key: &RegKey, executable: &Path) -> io::Result<()> {
        let bare = format!("\"{}\"", executable.display());
        if optional(key.get_value::<String, _>(NAME))?.is_some_and(|value| value == bare) {
            key.set_value(NAME, &command(executable))?;
        }
        Ok(())
    }

    pub fn upgrade() -> io::Result<()> {
        let user = RegKey::predef(HKEY_CURRENT_USER);
        match optional(user.open_subkey_with_flags(RUN, KEY_READ | KEY_SET_VALUE))? {
            Some(key) => upgrade_entry(&key, &std::env::current_exe()?),
            None => Ok(()),
        }
    }

    pub fn is_enabled() -> io::Result<bool> {
        let user = RegKey::predef(HKEY_CURRENT_USER);
        let Some(key) = optional(user.open_subkey(RUN))? else {
            return Ok(false);
        };
        if !registered(&key)? {
            return Ok(false);
        }
        // Task Manager can disable a Run entry without removing it.
        if let Some(approved) = optional(user.open_subkey(APPROVED))? {
            if let Some(value) = optional(approved.get_raw_value(NAME))? {
                return Ok(matches!(value.bytes.first(), Some(2 | 6)));
            }
        }
        Ok(true)
    }

    pub fn set_enabled(enabled: bool) -> io::Result<()> {
        let user = RegKey::predef(HKEY_CURRENT_USER);
        if enabled {
            let executable = std::env::current_exe()?;
            // Re-enabling also clears a previous Task Manager disable override.
            if let Some(approved) = optional(user.open_subkey_with_flags(APPROVED, KEY_SET_VALUE))?
            {
                optional(approved.delete_value(NAME))?;
            }
            let (key, _) = user.create_subkey(RUN)?;
            write_entry(&key, Some(&executable))
        } else {
            if let Some(key) = optional(user.open_subkey_with_flags(RUN, KEY_READ | KEY_SET_VALUE))?
            {
                write_entry(&key, None)?;
            }
            Ok(())
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn startup_entry_quotes_paths_and_preserves_other_programs() {
            // An isolated test key; never write to the real login startup list.
            let marker = tempfile::tempdir().unwrap();
            let path = format!(
                r"Software\Cijian\Tests\{}",
                marker.path().file_name().unwrap().to_string_lossy()
            );
            let user = RegKey::predef(HKEY_CURRENT_USER);
            let (key, _) = user.create_subkey(&path).unwrap();
            key.set_value("OtherApp", &"keep").unwrap();
            assert!(!registered(&key).unwrap());
            let executable = Path::new(r"C:\Program Files\词间\cijian.exe");
            write_entry(&key, Some(executable)).unwrap();
            assert!(registered(&key).unwrap());
            let silent = "\"C:\\Program Files\\词间\\cijian.exe\" --autostart";
            assert_eq!(key.get_value::<String, _>(NAME).unwrap(), silent);
            // An entry from an earlier version gains the flag; another executable's entry is kept.
            key.set_value(NAME, &"\"C:\\Program Files\\词间\\cijian.exe\"").unwrap();
            upgrade_entry(&key, Path::new(r"C:\dev\cijian.exe")).unwrap();
            assert_eq!(key.get_value::<String, _>(NAME).unwrap(), "\"C:\\Program Files\\词间\\cijian.exe\"");
            upgrade_entry(&key, executable).unwrap();
            assert_eq!(key.get_value::<String, _>(NAME).unwrap(), silent);
            write_entry(&key, None).unwrap();
            write_entry(&key, None).unwrap();
            assert!(!registered(&key).unwrap());
            assert_eq!(key.get_value::<String, _>("OtherApp").unwrap(), "keep");
            drop(key);
            user.delete_subkey_all(&path).unwrap();
        }
    }
}

#[cfg(windows)]
pub use platform::{is_enabled, set_enabled, upgrade};

#[cfg(not(windows))]
pub fn is_enabled() -> std::io::Result<bool> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "当前仅支持 Windows 开机自启动",
    ))
}

#[cfg(not(windows))]
pub fn set_enabled(_enabled: bool) -> std::io::Result<()> {
    is_enabled().map(|_| ())
}

/// Nothing is registered outside Windows.
#[cfg(not(windows))]
pub fn upgrade() -> std::io::Result<()> {
    Ok(())
}
