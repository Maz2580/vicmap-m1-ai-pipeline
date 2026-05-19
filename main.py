import time
import argparse
import logging
import schedule

from download import download_and_extract
from fme_runner import run_fme
from pozi_runner import run_pozi
from qa import perform_qa
from config import LOG_DIR


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "m1_automation.log"),
            logging.StreamHandler(),
        ],
    )


def m1_cycle():
    try:
        download_and_extract()
        run_fme()
        run_pozi()
        perform_qa()
        logging.getLogger(__name__).info("M1 cycle completed successfully.")
    except Exception as e:
        logging.getLogger(__name__).exception("Error in M1 cycle: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Run M1 automation cycle")
    parser.add_argument("--once", action="store_true", help="Run the cycle once and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    if args.once:
        m1_cycle()
        return

    # default: run once, then schedule weekly on Monday 06:00
    m1_cycle()
    schedule.every().monday.at("06:00").do(m1_cycle)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
