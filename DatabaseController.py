import os
import time
import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative


Base = sqlalchemy.ext.declarative.declarative_base()


class Alert(Base):
    __tablename__ = "alerts"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer)
    route = sqlalchemy.Column(sqlalchemy.String)
    time = sqlalchemy.Column(sqlalchemy.String)
    direction = sqlalchemy.Column(sqlalchemy.String)

    def __repr__(self):
        return "<Alert(id=%s, route=%s, time=%s, direction=%s, user_id=%s)>" % (
            repr(self.id),
            repr(self.route),
            repr(self.time),
            repr(self.direction),
            repr(self.user_id),
        )


class Notification(Base):
    __tablename__ = "notifications"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    hash = sqlalchemy.Column(sqlalchemy.String)
    heading = sqlalchemy.Column(sqlalchemy.String)
    text = sqlalchemy.Column(sqlalchemy.String)
    recipient = sqlalchemy.Column(sqlalchemy.String)
    sent = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    time_created = sqlalchemy.Column(sqlalchemy.DateTime, default=sqlalchemy.func.now())
    time_sent = sqlalchemy.Column(sqlalchemy.DateTime)

    # hash must either be none or unique
    __table_args__ = (sqlalchemy.UniqueConstraint("hash", name="unique_hash"),)

    def __repr__(self):
        return (
            "<Notification(id=%s, hash=%s, heading=%s, text=%s, recipient=%s, sent=%s, time_created=%s, time_sent=%s)>"
            % (
                repr(self.id),
                repr(self.hash),
                repr(self.heading),
                repr(self.text),
                repr(self.recipient),
                repr(self.sent),
                repr(self.time_created),
                repr(self.time_sent),
            )
        )


class Preference(Base):
    __tablename__ = "preferences"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer)
    key = sqlalchemy.Column(sqlalchemy.String)
    value = sqlalchemy.Column(sqlalchemy.String)

    # the user_id and key pair must be unique
    __table_args__ = (sqlalchemy.UniqueConstraint("user_id", "key"),)

    def __repr__(self):
        return "<Preference(id=%s, user_id=%s, key=%s, value=%s)>" % (
            repr(self.id),
            repr(self.user_id),
            repr(self.key),
            repr(self.value),
        )


class DatabaseController:
    def __init__(self, connection_string):
        engine = sqlalchemy.create_engine(connection_string)
        Base.metadata.create_all(engine)
        self._session_maker = sqlalchemy.orm.sessionmaker(bind=engine)

    def get_user_preference(self, user_id, key):
        with self._session_maker() as session:
            preference = (
                session.query(Preference)
                .filter(Preference.user_id == user_id)
                .filter(Preference.key == key)
                .first()
            )
            return preference.value if preference else None

    def set_user_preference(self, user_id, key, value):
        if self.get_user_preference(user_id, key) is None:
            with self._session_maker() as session:
                preference = Preference(user_id=user_id, key=key, value=value)
                session.add(preference)
                session.commit()
        else:
            Preference.query.filter_by(user_id=user_id, key=key).update(
                {"value": value}
            )

    def send_notification(self, recipient, text, heading=None, hash=None):
        if hash is None:
            hash = repr((time.time(), os.urandom(128)))
        if heading is None:
            heading = "General Alert"
        with self._session_maker() as session:
            notification = Notification(
                hash=hash, text=text, recipient=recipient, heading=heading, sent=False
            )
            session.add(notification)
            session.commit()

    def mark_notification_sent(self, notification_id):
        with self._session_maker() as session:
            notification = session.query(Notification).get(notification_id)
            notification.sent = True
            notification.time_sent = sqlalchemy.func.now()
            session.commit()

    def get_pending_notifications(self):
        with self._session_maker() as session:
            return list(
                session.query(Notification).filter(Notification.sent == False).all()
            )

    def new_alert(self, user_id, route, time, direction):
        with self._session_maker() as session:
            alert = Alert(user_id=user_id, route=route, time=time, direction=direction)
            session.add(alert)
            session.commit()

    def delete_alert(self, user_id, alert_id):
        with self._session_maker() as session:
            # if the user_id matches
            alert = (
                session.query(Alert)
                .filter(Alert.user_id == user_id)
                .filter(Alert.id == alert_id)
                .first()
            )

            if alert:
                session.delete(alert)
                session.commit()
                return True
            else:
                return False

    def get_alerts(self, user_id=None):
        with self._session_maker() as session:
            if user_id:
                return session.query(Alert).filter(Alert.user_id == user_id).all()
            else:
                return session.query(Alert).all()
