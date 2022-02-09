backup_size_header
==================

Authors: 


* Miku Laitinen / `Avoin.Systems <https://avoin.systems>`_

Overrides the default backup method of Odoo and adds the ``Content-Length`` header
in the backup response.

Add this module to ``server_wide_modules``.

Further Explanation
-------------------

WITHOUT ``backup_size_header``\ : You go to the database manager, take a backup of a large database, the worker times out. 
You end up with a broken backup file, but you don't know that, because your browser doesn't know how large the file 
is supposed to be. You might get the sense that everything went fine and you have a full backup.

WITH ``backup_size_header``\ : You take a backup, Odoo sends the ``Content-Length`` HTTP header to your browser, so your
browser knows how large file it expects to receive. Odoo times out, and your browser tells you that the download failed.
You don't have the false sense of having successfully downloaded the backup file.
