"""
Dangerous patterns — known dangerous shell commands and patterns.
"""

from __future__ import annotations

# (regex_pattern, reason) tuples
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Destructive file operations
    (r"rm\s+-[rf]*\s+/\s*$", "Delete root filesystem"),
    (r"rm\s+-[rf]*\s+/\*", "Delete root filesystem contents"),
    (r"rm\s+-[rf]*\s+~\s*$", "Delete home directory"),
    (r"rm\s+-[rf]*\s+~/\*", "Delete home directory contents"),
    (r"rm\s+-[rf]*\s+\.\s*$", "Delete current directory"),
    (r"mkfs\.", "Format filesystem"),
    (r"dd\s+if=.*of=/dev/", "Raw disk write"),

    # Fork bombs and resource exhaustion
    (r":\(\)\{.*\|.*\}", "Fork bomb"),
    (r"while\s+true.*fork", "Fork bomb variant"),

    # Dangerous redirects
    (r">\s*/dev/sd[a-z]", "Write to disk device"),
    (r">\s*/dev/null\s+2>&1\s*&\s*$", "Background with no output (suspicious)"),

    # Privilege escalation
    (r"chmod\s+[0-7]*777", "World-writable permissions"),
    (r"chmod\s+-R\s+777", "Recursive world-writable"),
    (r"chown\s+-R\s+root", "Recursive ownership to root"),

    # Network exfiltration
    (r"curl.*\|\s*bash", "Pipe curl to bash"),
    (r"wget.*\|\s*sh", "Pipe wget to shell"),
    (r"curl.*\|\s*sh", "Pipe curl to shell"),

    # History/evidence tampering
    (r"history\s+-c", "Clear shell history"),
    (r"shred\s+.*history", "Shred history file"),
    (r">\s*~/\.bash_history", "Truncate bash history"),

    # Crypto mining indicators
    (r"xmrig|minerd|cpuminer", "Cryptocurrency miner"),

    # Reverse shells
    (r"bash\s+-i\s+>&\s+/dev/tcp/", "Reverse shell"),
    (r"nc\s+-[elp]", "Netcat listener"),
    (r"python.*socket.*connect", "Python reverse shell"),

    # System modification
    (r"systemctl\s+(disable|mask|stop)\s+(firewall|iptables|ufw)", "Disable firewall"),
    (r"iptables\s+-F", "Flush firewall rules"),
    (r"echo\s+.*>\s*/etc/", "Write to /etc/"),
    (r"crontab\s+-r", "Remove all cron jobs"),

    # Data exfiltration
    (r"tar\s+.*\|\s*(curl|wget|nc)", "Archive and exfiltrate"),
    (r"base64.*\|\s*(curl|wget)", "Encode and exfiltrate"),
]

# Commands that are always safe (read-only, no side effects)
SAFE_COMMANDS: set[str] = {
    # File reading
    "cat", "head", "tail", "less", "more", "bat",
    "wc", "sort", "uniq", "cut", "tr", "awk", "sed",  # sed is read-only without -i
    "tee",

    # Search
    "find", "grep", "egrep", "fgrep", "rg", "ag", "fd",
    "locate", "which", "whereis", "whatis", "type",

    # File info
    "ls", "ll", "la", "dir", "stat", "file", "du", "df",
    "tree", "realpath", "basename", "dirname", "readlink",

    # Text processing
    "echo", "printf", "diff", "comm", "cmp", "md5sum",
    "sha256sum", "sha1sum", "xxd", "hexdump",

    # System info
    "date", "cal", "uptime", "hostname", "uname",
    "whoami", "id", "groups", "env", "printenv",
    "arch", "nproc", "lscpu", "free", "top",

    # Process info
    "ps", "pgrep", "jobs", "lsof",

    # Network info
    "ping", "traceroute", "nslookup", "dig", "host",
    "ifconfig", "ip", "ss", "netstat",

    # Development (read-only)
    "git log", "git status", "git diff", "git show",
    "git branch", "git tag", "git remote",

    # Version checks
    "python", "python3", "node", "npm", "go", "rustc",
    "java", "ruby", "php", "perl",

    # Help
    "man", "help", "info",

    # Misc
    "true", "false", "test", "expr", "bc", "seq",
    "yes", "sleep", "clear", "reset", "tput",
    "jq", "yq", "xmllint",
}
