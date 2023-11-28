import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative


Base = sqlalchemy.ext.declarative.declarative_base()


class Alert(Base):
    __tablename__ = "alerts"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    route = sqlalchemy.Column(sqlalchemy.String)
    time = sqlalchemy.Column(sqlalchemy.String)
    direction = sqlalchemy.Column(sqlalchemy.String)
    user_id = sqlalchemy.Column(sqlalchemy.Integer)

    def __repr__(self):
        return (
            "<Alert(id='%s', route='%s', time='%s', direction='%s', user_id='%s')>"
            % (
                self.id,
                self.route,
                self.time,
                self.direction,
                self.user_id,
            )
        )


class Notification(Base):
    __tablename__ = "notifications"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    hash = sqlalchemy.Column(sqlalchemy.String)
    text = sqlalchemy.Column(sqlalchemy.String)
    sent = sqlalchemy.Column(sqlalchemy.Boolean)

    def mark_sent(self):
        self.sent = True

    # hash must either be none or unique
    __table_args__ = (sqlalchemy.UniqueConstraint("hash", name="unique_hash"),)

    def __repr__(self):
        return "<Notification(id='%s', alert='%s', sent='%s')>" % (
            self.id,
            self.alert,
            self.sent,
        )


class Preference(Base):
    __tablename__ = "preferences"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer)
    user = sqlalchemy.orm.relationship("User", backref="preferences")
    key = sqlalchemy.Column(sqlalchemy.String)
    value = sqlalchemy.Column(sqlalchemy.String)

    # the user_id and key pair must be unique
    __table_args__ = (sqlalchemy.UniqueConstraint("user_id", "key"),)

    def __repr__(self):
        return "<Preference(id='%s', user_id='%s', key='%s', value='%s')>" % (
            self.id,
            self.user_id,
            self.key,
            self.value,
        )


class DatabaseController:
    def __init__(self, connection_string):
        engine = sqlalchemy.create_engine(connection_string)
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

    def send_notification(self, hash, text):
        with self._session_maker() as session:
            notification = Notification(hash=hash, text=text)
            session.add(notification)
            session.commit()

    def get_pending_notifications(self):
        with self._session_maker() as session:
            return (
                session.query(Notification)
                .filter(Notification.sent == False)
                .join(Alert)
                .filter(Alert.time == "now")
                .all()
            )
    
    def get_alerts(user_id):
        with self._session_maker() as session:
            
