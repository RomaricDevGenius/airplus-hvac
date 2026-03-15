"""
Backend MySQL/MariaDB qui accepte MariaDB 10.4+ (Django 5 exige 10.6 par défaut).
Utiliser ENGINE "config.db_backends.mysql" dans DATABASES pour l'activer.
"""
from django.utils.functional import cached_property

# Réutiliser tout le backend MySQL officiel
from django.db.backends.mysql import base as mysql_base
from django.db.backends.mysql.features import DatabaseFeatures as MySQLDatabaseFeatures


class DatabaseFeatures(MySQLDatabaseFeatures):
    """Accepte MariaDB 10.4+ au lieu du minimum 10.6 requis par Django 5."""

    @cached_property
    def minimum_database_version(self):
        if self.connection.mysql_is_mariadb:
            return (10, 4)  # MariaDB 10.4 au lieu de (10, 6)
        return (8, 0, 11)  # MySQL inchangé


class DatabaseWrapper(mysql_base.DatabaseWrapper):
    features_class = DatabaseFeatures


# Exposer tout ce que Django charge depuis ce module
Database = mysql_base.Database
django_conversions = mysql_base.django_conversions
server_version_re = mysql_base.server_version_re
CursorWrapper = mysql_base.CursorWrapper
IntegrityError = mysql_base.IntegrityError
