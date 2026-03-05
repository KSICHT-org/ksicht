# Activate virtual environment
.\.venv\Scripts\Activate.ps1;

# Set environment variables
$env:DEBUG = 1;

$env:DEBUG_TOOLBAR = 1;

# change DATABASE_DSN according to your settings
$env:DATABASE_DSN = "postgresql://postgres:postgres@localhost:5432/ksicht";

$env:CFLAGS="-Wno-error=implicit-function-declaration";

# Load .env variables
# Source - https://stackoverflow.com/a/74839464
# Posted by jeiea, modified by community. See post 'Timeline' for change history
# Retrieved 2026-03-02, License - CC BY-SA 4.0
Get-Content .env | foreach {
  $name, $value = $_.split('=')
  if ([string]::IsNullOrWhiteSpace($name) -or $name.Contains('#')) {
    # skip empty or comment line in ENV file
    return
  }
  Set-Content env:\$name $value
}
