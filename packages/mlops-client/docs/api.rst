API reference
=============

Starting a run
--------------

.. autofunction:: mlops.init

.. autofunction:: mlops.run.current_run

Runs
----

.. autoclass:: mlops.run.Run
   :members: track, log_metric, log_metrics, log_image, log_audio, log_text, log_figure,
             log_distribution, log_params, upload_artifact, close

.. autoexception:: mlops.run.RunError
