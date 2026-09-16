"""labflash — command-line entry point."""
import argparse
import sys


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="labflash", description="ESP32-S3 Bootloader & OTA Lab CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="environment check (BL-007 stub)")
    sub.add_parser("identify", help="(later epic) map boards by LABID")
    sub.add_parser("info", help="(later epic) show board identity/versions")
    sub.add_parser("flash", help="(later epic) flash a board")
    sub.add_parser("recover", help="(later epic) erase + factory flash")
    sub.add_parser("update", help="(later epic) OTA over BLE/WiFi")

    args = p.parse_args(argv)

    if args.cmd == "doctor":
        from labflash.doctor import main as doctor_main
        return doctor_main()
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
