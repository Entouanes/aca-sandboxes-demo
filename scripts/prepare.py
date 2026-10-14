import secrets
import subprocess


def main():
    current = subprocess.run(
        ["azd", "env", "get-value", "DEMO_API_KEY"],
        capture_output=True,
        text=True,
        check=False,
    )
    if current.returncode != 0 or not current.stdout.strip():
        subprocess.run(
            ["azd", "env", "set", "DEMO_API_KEY", secrets.token_urlsafe(32)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        print("Generated a presenter key in the local azd environment (not printed).")
    print("After azd up, retrieve your presenter key with: azd env get-value DEMO_API_KEY")


if __name__ == "__main__":
    main()
