//! Windows login startup, scoped to the current user.

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

    fn write_entry(key: &RegKey, executable: Option<&Path>) -> io::Result<()> {
        if let Some(executable) = executable {
            // Windows Run commands must quote the full executable path.
            key.set_value(NAME, &format!("\"{}\"", executable.display()))
        } else {
            optional(key.delete_value(NAME)).map(|_| ())
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
            write_entry(&key, Some(Path::new(r"C:\Program Files\词间\cijian.exe"))).unwrap();
            assert!(registered(&key).unwrap());
            assert_eq!(
                key.get_value::<String, _>(NAME).unwrap(),
                "\"C:\\Program Files\\词间\\cijian.exe\""
            );
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
pub use platform::{is_enabled, set_enabled};

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
