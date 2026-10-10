from unittest.mock import patch

import scraping_scheduler


class TestMain:
    """AEK-84 : le reloader Werkzeug lançait deux processus, donc deux schedulers."""

    def _run_main(self, debug: bool):
        with (
            patch("scraping_scheduler.BackgroundScheduler") as scheduler_cls,
            patch("scraping_scheduler.app.run") as app_run,
            patch("scraping_scheduler.get_settings") as get_settings,
            patch("scraping_scheduler.atexit.register"),
        ):
            get_settings.return_value.debug = debug
            scraping_scheduler.main()
        return scheduler_cls, app_run

    def test_debug_off_and_reloader_disabled_by_default(self):
        _, app_run = self._run_main(debug=False)
        app_run.assert_called_once()
        kwargs = app_run.call_args.kwargs
        assert kwargs["debug"] is False
        assert kwargs["use_reloader"] is False

    def test_reloader_stays_disabled_in_debug_mode(self):
        _, app_run = self._run_main(debug=True)
        kwargs = app_run.call_args.kwargs
        assert kwargs["debug"] is True
        assert kwargs["use_reloader"] is False

    def test_single_scheduler_with_one_daily_job(self):
        scheduler_cls, _ = self._run_main(debug=False)
        scheduler_cls.assert_called_once()
        scheduler = scheduler_cls.return_value
        scheduler.add_job.assert_called_once()
        assert scheduler.add_job.call_args.kwargs["id"] == "daily_scraping"
        scheduler.start.assert_called_once()
