from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
import os

load_dotenv()

aws_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")


#configuración de la app
app = Flask(__name__)
app.secret_key = "clave-secreta-turnomed"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

DB_PATH = "database/turnomed.db"
UPLOAD_FOLDER = "static/imagenes/medicos"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
#base da datos

def get_conn():
    
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def archivo_permitido(nombre_archivo):
    return (
        "." in nombre_archivo and
        nombre_archivo.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )
def inicializar_base_de_datos():
    conn = get_conn()
    cursor = conn.cursor()
#usuarios, medicos, horarios y turnos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            dni TEXT,
            telefono TEXT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'paciente',
            fecha_nacimiento TEXT,
            activo INTEGER DEFAULT 1
        )
    """)
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN fecha_nacimiento TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicos (
            id_medico INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            especialidad TEXT NOT NULL,
            email TEXT,
            telefono TEXT,
            foto TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS horarios (
            id_horario INTEGER PRIMARY KEY AUTOINCREMENT,
            id_medico INTEGER NOT NULL,
            especialidad TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            ocupado INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (id_medico) REFERENCES medicos(id_medico)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS turnos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_paciente INTEGER NOT NULL,
            id_horario INTEGER NOT NULL,
            id_medico INTEGER NOT NULL,
            paciente TEXT NOT NULL,
            especialidad TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Confirmado',
            llamado INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (id_paciente) REFERENCES usuarios(id_usuario),
            FOREIGN KEY (id_horario) REFERENCES horarios(id_horario),
            FOREIGN KEY (id_medico) REFERENCES medicos(id_medico)
        )
    """)

    conn.commit()
    conn.close()

#datos iniciales para pruebas
def crear_datos_iniciales():
    conn = get_conn()
    cursor = conn.cursor()

    usuarios = [
        ("Admin", "Sistema", "00000000", "1122334455", "admin@turnomed.com", generate_password_hash("admin123"), "admin"),
        ("Juan", "Pérez", "11111111", "1133445566", "paciente@turnomed.com", generate_password_hash("paciente123"), "paciente"),
        ("Carlos", "Gómez", "22222222", "1144556677", "medico@turnomed.com", generate_password_hash("medico123"), "medico"),
    ]

    for usuario in usuarios:
        existe = cursor.execute(
            "SELECT * FROM usuarios WHERE email = ?",
            (usuario[4],)
        ).fetchone()

        if not existe:
            cursor.execute("""
                INSERT INTO usuarios
                (nombre, apellido, dni, telefono, email, password, rol)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, usuario)

    medicos = [
        ("Carlos", "Gómez", "Clínica Médica", "medico@turnomed.com", "1144556677", "medico_default.png"),
        ("Laura", "Ruiz", "Pediatría", "laura.ruiz@turnomed.com", "1166778899", "medico_default.png"),
    ]

    for medico in medicos:
        existe = cursor.execute("""
            SELECT * FROM medicos
            WHERE nombre = ? AND apellido = ? AND especialidad = ?
        """, (medico[0], medico[1], medico[2])).fetchone()

        if not existe:
            cursor.execute("""
                INSERT INTO medicos
                (nombre, apellido, especialidad, email, telefono, foto, activo)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, medico)

    conn.commit()
    conn.close()


inicializar_base_de_datos()
crear_datos_iniciales()

#user model para flask-login
class User(UserMixin):
    def __init__(self, usuario):
        self.id = str(usuario["id_usuario"])
        self.nombre = usuario["nombre"]
        self.apellido = usuario["apellido"]
        self.email = usuario["email"]
        self.rol = usuario["rol"]


@login_manager.user_loader
def load_user(user_id):
    conn = get_conn()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE id_usuario = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    if usuario:
        return User(usuario)

    return None

#funciones para manejar usuarios, médicos, horarios y turnos
def buscar_usuario_por_email(email):
    conn = get_conn()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE email = ?",
        (email,)
    ).fetchone()
    conn.close()
    return usuario


def registrar_paciente(nombre, apellido, dni, telefono, email, password, fecha_nacimiento=None):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO usuarios
        (nombre, apellido, dni, telefono, email, password, rol, fecha_nacimiento, activo)
        VALUES (?, ?, ?, ?, ?, ?, 'paciente', ?, 1)
    """, (
        nombre,
        apellido,
        dni,
        telefono,
        email.strip().lower(),
        generate_password_hash(password),
        fecha_nacimiento
    ))

    conn.commit()
    conn.close()


def obtener_pacientes(busqueda=None):
    conn = get_conn()

    if busqueda:
        termino = f"%{busqueda.strip()}%"

        pacientes = conn.execute("""
            SELECT *
            FROM usuarios
            WHERE rol = 'paciente'
            AND (
                nombre LIKE ?
                OR apellido LIKE ?
                OR dni LIKE ?
                OR email LIKE ?
                OR telefono LIKE ?
            )
            ORDER BY apellido, nombre
        """, (
            termino,
            termino,
            termino,
            termino,
            termino
        )).fetchall()
    else:
        pacientes = conn.execute("""
            SELECT *
            FROM usuarios
            WHERE rol = 'paciente'
            ORDER BY apellido, nombre
        """).fetchall()

    conn.close()
    return pacientes

def obtener_pacientes_admin(busqueda=None, estado="activos"):
    conn = get_conn()

    query = """
        SELECT *
        FROM usuarios
        WHERE rol = 'paciente'
    """

    params = []

    if estado == "activos":
        query += " AND activo = 1"

    elif estado == "inactivos":
        query += " AND activo = 0"

    if busqueda:
        termino = f"%{busqueda.strip()}%"
        query += """
            AND (
                nombre LIKE ?
                OR apellido LIKE ?
                OR dni LIKE ?
                OR email LIKE ?
                OR telefono LIKE ?
            )
        """
        params.extend([termino, termino, termino, termino, termino])

    query += " ORDER BY activo DESC, apellido, nombre"

    pacientes = conn.execute(query, params).fetchall()
    conn.close()
    return pacientes


def calcular_edad(fecha_nacimiento):
    if not fecha_nacimiento:
        return "Sin dato"

    try:
        nacimiento = datetime.strptime(fecha_nacimiento, "%Y-%m-%d")
        hoy = datetime.today()

        edad = hoy.year - nacimiento.year

        if (hoy.month, hoy.day) < (nacimiento.month, nacimiento.day):
            edad -= 1

        return edad

    except ValueError:
        return "Sin dato"
    
def obtener_medicos(busqueda=None, especialidad=None, estado="activos"):
    conn = get_conn()

    query = """
        SELECT *
        FROM medicos
        WHERE 1 = 1
    """

    params = []

    if estado == "activos":
        query += " AND activo = 1"

    elif estado == "inactivos":
        query += " AND activo = 0"

    if busqueda:
        termino = f"%{busqueda.strip()}%"
        query += """
            AND (
                nombre LIKE ?
                OR apellido LIKE ?
                OR email LIKE ?
            )
        """
        params.extend([termino, termino, termino])

    if especialidad:
        query += " AND especialidad = ?"
        params.append(especialidad)

    query += " ORDER BY activo DESC, especialidad, apellido, nombre"

    medicos = conn.execute(query, params).fetchall()
    conn.close()
    return medicos

def obtener_medicos_por_disponibilidad(especialidad=None, fecha=None):
    conn = get_conn()

    query = """
        SELECT DISTINCT medicos.*
        FROM medicos
        INNER JOIN horarios ON medicos.id_medico = horarios.id_medico
        WHERE medicos.activo = 1
        AND horarios.ocupado = 0
    """

    params = []

    if especialidad:
        query += " AND horarios.especialidad = ?"
        params.append(especialidad)

    if fecha:
        query += " AND horarios.fecha = ?"
        params.append(fecha)

    query += " ORDER BY medicos.apellido, medicos.nombre"

    medicos = conn.execute(query, params).fetchall()
    conn.close()
    return medicos

def obtener_horarios_disponibles():
    conn = get_conn()
    horarios = conn.execute("""
        SELECT horarios.*, medicos.nombre, medicos.apellido
        FROM horarios
        INNER JOIN medicos ON horarios.id_medico = medicos.id_medico
        WHERE horarios.ocupado = 0
        ORDER BY horarios.fecha, horarios.hora
    """).fetchall()
    conn.close()
    return horarios

def obtener_horarios_filtrados(especialidad=None, id_medico=None, fecha=None):
    conn = get_conn()

    query = """
        SELECT
            horarios.*,
            medicos.nombre AS medico_nombre,
            medicos.apellido AS medico_apellido
        FROM horarios
        INNER JOIN medicos
        ON horarios.id_medico = medicos.id_medico
        WHERE horarios.ocupado = 0
        AND medicos.activo = 1
    """

    params = []

    if especialidad:
        query += " AND horarios.especialidad = ?"
        params.append(especialidad)

    if id_medico:
        query += " AND horarios.id_medico = ?"
        params.append(id_medico)

    if fecha:
        query += " AND horarios.fecha = ?"
        params.append(fecha)

    query += " ORDER BY horarios.fecha, horarios.hora"

    horarios = conn.execute(query, params).fetchall()
    conn.close()
    return horarios

def obtener_fechas_disponibles(especialidad=None, id_medico=None):
    conn = get_conn()

    query = """
        SELECT DISTINCT horarios.fecha
        FROM horarios
        INNER JOIN medicos
        ON horarios.id_medico = medicos.id_medico
        WHERE horarios.ocupado = 0
        AND medicos.activo = 1
    """

    params = []

    if especialidad:
        query += " AND horarios.especialidad = ?"
        params.append(especialidad)

    if id_medico:
        query += " AND horarios.id_medico = ?"
        params.append(id_medico)

    query += " ORDER BY horarios.fecha"

    fechas = conn.execute(query, params).fetchall()
    conn.close()
    return fechas

def generar_horarios_automaticos(id_medico, fecha, hora_inicio, hora_fin, frecuencia):
    conn = get_conn()
    cursor = conn.cursor()

    medico = cursor.execute("""
        SELECT *
        FROM medicos
        WHERE id_medico = ?
        AND activo = 1
    """, (id_medico,)).fetchone()

    if not medico:
        conn.close()
        return 0, "Médico no encontrado o inactivo."

    try:
        inicio = datetime.strptime(hora_inicio, "%H:%M")
        fin = datetime.strptime(hora_fin, "%H:%M")
        frecuencia = int(frecuencia)
    except ValueError:
        conn.close()
        return 0, "Datos de horario inválidos."

    if frecuencia <= 0:
        conn.close()
        return 0, "La frecuencia debe ser mayor a 0."

    if inicio > fin:
        conn.close()
        return 0, "La hora de inicio no puede ser mayor a la hora de fin."

    cantidad_generada = 0
    hora_actual = inicio

    while hora_actual <= fin:
        hora_texto = hora_actual.strftime("%H:%M")

        existe = cursor.execute("""
            SELECT *
            FROM horarios
            WHERE id_medico = ?
            AND fecha = ?
            AND hora = ?
        """, (id_medico, fecha, hora_texto)).fetchone()

        if not existe:
            cursor.execute("""
                INSERT INTO horarios
                (id_medico, especialidad, fecha, hora, ocupado)
                VALUES (?, ?, ?, ?, 0)
            """, (
                id_medico,
                medico["especialidad"],
                fecha,
                hora_texto
            ))

            cantidad_generada += 1

        hora_actual += timedelta(minutes=frecuencia)

    conn.commit()
    conn.close()

    return cantidad_generada, "Horarios generados correctamente."

def obtener_turnos():
    conn = get_conn()
    turnos = conn.execute("""
        SELECT
            turnos.*,
            usuarios.nombre AS paciente_nombre,
            usuarios.apellido AS paciente_apellido,
            medicos.nombre AS medico_nombre,
            medicos.apellido AS medico_apellido
        FROM turnos
        INNER JOIN usuarios ON turnos.id_paciente = usuarios.id_usuario
        INNER JOIN medicos ON turnos.id_medico = medicos.id_medico
        ORDER BY turnos.fecha, turnos.hora
    """).fetchall()
    conn.close()
    return turnos


def obtener_turnos_por_paciente(id_paciente):
    conn = get_conn()
    turnos = conn.execute("""
        SELECT
            turnos.*,
            medicos.nombre AS medico_nombre,
            medicos.apellido AS medico_apellido
        FROM turnos
        INNER JOIN medicos ON turnos.id_medico = medicos.id_medico
        WHERE turnos.id_paciente = ?
        ORDER BY turnos.fecha, turnos.hora
    """, (id_paciente,)).fetchall()
    conn.close()
    return turnos


def obtener_turnos_por_medico(id_medico, fecha=None):
    conn = get_conn()

    query = """
        SELECT
            turnos.*,
            usuarios.nombre AS paciente_nombre,
            usuarios.apellido AS paciente_apellido,
            usuarios.telefono,
            medicos.nombre AS medico_nombre,
            medicos.apellido AS medico_apellido
        FROM turnos
        INNER JOIN usuarios ON turnos.id_paciente = usuarios.id_usuario
        INNER JOIN medicos ON turnos.id_medico = medicos.id_medico
        WHERE turnos.id_medico = ?
    """

    params = [id_medico]

    if fecha:
        query += " AND turnos.fecha = ?"
        params.append(fecha)

    query += " ORDER BY turnos.fecha, turnos.hora"

    turnos = conn.execute(query, params).fetchall()
    conn.close()
    return turnos

def obtener_medico_por_email(email):
    conn = get_conn()
    medico = conn.execute("""
        SELECT * FROM medicos
        WHERE email = ?
    """, (email.strip().lower(),)).fetchone()
    conn.close()
    return medico
def obtener_usuario_por_id(id_usuario):
    conn = get_conn()

    usuario = conn.execute("""
        SELECT *
        FROM usuarios
        WHERE id_usuario = ?
    """, (id_usuario,)).fetchone()

    conn.close()
    return usuario


def actualizar_usuario(
    id_usuario,
    nombre,
    apellido,
    dni,
    telefono,
    email,
    fecha_nacimiento=None
):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET
            nombre = ?,
            apellido = ?,
            dni = ?,
            telefono = ?,
            email = ?,
            fecha_nacimiento = ?
        WHERE id_usuario = ?
    """, (
        nombre,
        apellido,
        dni,
        telefono,
        email,
        fecha_nacimiento,
        id_usuario
    ))

    conn.commit()
    conn.close()


def cambiar_password_usuario(
    id_usuario,
    nueva_password
):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET password = ?
        WHERE id_usuario = ?
    """, (
        generate_password_hash(nueva_password),
        id_usuario
    ))

    conn.commit()
    conn.close()
#rutas de autenticación, administración, paciente y médico
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        usuario = buscar_usuario_por_email(email)

        if not usuario:
            flash("No existe un usuario registrado con ese correo.")
            return redirect(url_for("login"))

        if not check_password_hash(usuario["password"], password):
            flash("La contraseña ingresada es incorrecta.")
            return redirect(url_for("login"))

        user = User(usuario)
        login_user(user)

        if user.rol == "admin":
            flash(f"Bienvenido/a {user.nombre}.")
            return redirect(url_for("admin"))

        if user.rol == "paciente":
            flash(f"Bienvenido/a {user.nombre}.")
            return redirect(url_for("paciente"))

        if user.rol == "medico":
            flash(f"Bienvenido/a Dr/a {user.apellido}.")
            return redirect(url_for("medico"))

        flash("El usuario no tiene un rol válido asignado.")
        logout_user()
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        try:
            registrar_paciente(
                request.form["nombre"],
                request.form["apellido"],
                request.form["dni"],
                request.form["telefono"],
                request.form["email"],
                request.form["password"],
                request.form.get("fecha_nacimiento")
            )
            flash("Registro exitoso. Ya podés iniciar sesión.")
            return redirect(url_for("login"))
        except Exception:
            flash("No se pudo registrar. El correo ya puede estar registrado.")
            return redirect(url_for("registro"))

    return render_template("registro.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

#panel admin
@app.route("/admin")
@login_required
def admin():

    if current_user.rol != "admin":
        flash("No tenés permiso para ingresar al panel de administración.")
        return redirect(url_for("login"))

    filtro_especialidad = request.args.get("especialidad", "")
    filtro_medico = request.args.get("id_medico", "")
    filtro_fecha = request.args.get("fecha", "")
    busqueda_paciente = request.args.get("buscar_paciente", "")

    medicos_filtrados = obtener_medicos(
        especialidad=filtro_especialidad if filtro_especialidad else None
    )

    fechas_disponibles = obtener_fechas_disponibles(
        filtro_especialidad if filtro_especialidad else None,
        filtro_medico if filtro_medico else None
    )

    horarios = obtener_horarios_filtrados(
        filtro_especialidad if filtro_especialidad else None,
        filtro_medico if filtro_medico else None,
        filtro_fecha if filtro_fecha else None
    )

    return render_template(
        "admin.html",
        usuario=current_user,
        pacientes=obtener_pacientes(busqueda_paciente),
        busqueda_paciente=busqueda_paciente,
        medicos=medicos_filtrados,
        especialidades=obtener_especialidades(),
        fechas_disponibles=fechas_disponibles,
        horarios=horarios,
        turnos=obtener_turnos(),
        filtro_especialidad=filtro_especialidad,
        filtro_medico=filtro_medico,
        filtro_fecha=filtro_fecha
    )

@app.route("/admin/agregar_medico", methods=["POST"])
@login_required
def agregar_medico():

    if current_user.rol != "admin":
        flash("No tenés permiso para realizar esta acción.")
        return redirect(url_for("login"))

    nombre = request.form["nombre"]
    apellido = request.form["apellido"]
    especialidad = request.form["especialidad"]
    email = request.form["email"].strip().lower()
    telefono = request.form["telefono"]
    password_inicial = request.form["password"]

    foto_archivo = request.files.get("foto")
    nombre_foto = "medico_default.png"

    if foto_archivo and foto_archivo.filename != "":

        if not archivo_permitido(foto_archivo.filename):
            flash("Formato de imagen no permitido. Usá PNG, JPG, JPEG o WEBP.")
            return redirect(url_for("admin"))

        nombre_seguro = secure_filename(foto_archivo.filename)
        nombre_foto = f"{email.replace('@', '_').replace('.', '_')}_{nombre_seguro}"
        ruta_foto = os.path.join(app.config["UPLOAD_FOLDER"], nombre_foto)

        foto_archivo.save(ruta_foto)

    conn = get_conn()
    cursor = conn.cursor()

    try:
        usuario_existente = cursor.execute("""
            SELECT *
            FROM usuarios
            WHERE email = ?
        """, (email,)).fetchone()

        if usuario_existente:
            conn.close()
            flash("Ya existe un usuario registrado con ese correo.")
            return redirect(url_for("admin"))

        cursor.execute("""
            INSERT INTO usuarios
            (
                nombre,
                apellido,
                dni,
                telefono,
                email,
                password,
                rol
            )
            VALUES (?, ?, ?, ?, ?, ?, 'medico')
        """, (
            nombre,
            apellido,
            "",
            telefono,
            email,
            generate_password_hash(password_inicial)
        ))

        cursor.execute("""
            INSERT INTO medicos
            (
                nombre,
                apellido,
                especialidad,
                email,
                telefono,
                foto,
                activo
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            nombre,
            apellido,
            especialidad,
            email,
            telefono,
            nombre_foto
        ))

        conn.commit()
        flash("Médico agregado correctamente. Ya puede iniciar sesión con su email y contraseña inicial.")

    except Exception:
        flash("No se pudo agregar el médico. Revisá los datos cargados.")

    conn.close()
    return redirect(url_for("admin"))


@app.route("/cargar_horario", methods=["POST"])
@login_required
def cargar_horario_route():
    if current_user.rol != "admin":
        flash("No tenés permiso para cargar horarios.")
        return redirect(url_for("login"))

    id_medico = request.form["id_medico"]
    fecha = request.form["fecha"]
    hora = request.form["hora"]

    conn = get_conn()
    cursor = conn.cursor()

    medico = cursor.execute("""
        SELECT * FROM medicos
        WHERE id_medico = ?
    """, (id_medico,)).fetchone()

    if not medico:
        conn.close()
        flash("Médico no encontrado.")
        return redirect(url_for("admin"))

    existe = cursor.execute("""
        SELECT * FROM horarios
        WHERE id_medico = ? AND fecha = ? AND hora = ?
    """, (id_medico, fecha, hora)).fetchone()

    if existe:
        conn.close()
        flash("Ese horario ya está cargado para el médico seleccionado.")
        return redirect(url_for("admin"))

    cursor.execute("""
        INSERT INTO horarios
        (id_medico, especialidad, fecha, hora, ocupado)
        VALUES (?, ?, ?, ?, 0)
    """, (id_medico, medico["especialidad"], fecha, hora))

    conn.commit()
    conn.close()

    flash("Horario cargado correctamente.")
    return redirect(url_for("admin"))


@app.route("/asignar_turno", methods=["POST"])
@login_required
def asignar_turno_route():
    if current_user.rol != "admin":
        flash("No tenés permiso para asignar turnos.")
        return redirect(url_for("login"))

    id_paciente = request.form["id_paciente"]
    id_horario = request.form["id_horario"]

    conn = get_conn()
    cursor = conn.cursor()

    horario = cursor.execute("""
        SELECT horarios.*, medicos.nombre, medicos.apellido
        FROM horarios
        INNER JOIN medicos ON horarios.id_medico = medicos.id_medico
        WHERE horarios.id_horario = ? AND horarios.ocupado = 0
    """, (id_horario,)).fetchone()

    if not horario:
        conn.close()
        flash("El horario ya está ocupado o no existe.")
        return redirect(url_for("admin"))

    paciente = cursor.execute("""
        SELECT * FROM usuarios
        WHERE id_usuario = ?
    """, (id_paciente,)).fetchone()

    if not paciente:
        conn.close()
        flash("Paciente no encontrado.")
        return redirect(url_for("admin"))

    nombre_paciente = f"{paciente['nombre']} {paciente['apellido']}"

    cursor.execute("""
        INSERT INTO turnos
        (id_paciente, id_horario, id_medico, paciente, especialidad, fecha, hora, estado, llamado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Confirmado', 0)
    """, (
        id_paciente,
        id_horario,
        horario["id_medico"],
        nombre_paciente,
        horario["especialidad"],
        horario["fecha"],
        horario["hora"]
    ))

    cursor.execute("""
        UPDATE horarios
        SET ocupado = 1
        WHERE id_horario = ?
    """, (id_horario,))

    conn.commit()
    conn.close()

    flash("Turno asignado correctamente.")
    return redirect(url_for("admin"))


@app.route("/cancelar_turno/<int:id_turno>", methods=["POST"])
@login_required
def cancelar_turno(id_turno):
    if current_user.rol != "admin":
        flash("No tenés permiso para cancelar turnos desde administración.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    turno = cursor.execute("""
        SELECT * FROM turnos
        WHERE id = ?
    """, (id_turno,)).fetchone()

    if turno:
        cursor.execute("""
            UPDATE horarios
            SET ocupado = 0
            WHERE id_horario = ?
        """, (turno["id_horario"],))

        cursor.execute("""
            UPDATE turnos
            SET estado = 'Cancelado'
            WHERE id = ?
        """, (id_turno,))

        conn.commit()
        flash("Turno cancelado correctamente. El horario volvió a estar disponible.")
    else:
        flash("Turno no encontrado.")

    conn.close()
    return redirect(url_for("admin"))
#panel paciente
def obtener_especialidades():
    conn = get_conn()
    especialidades = conn.execute("""
        SELECT DISTINCT especialidad
        FROM medicos
        WHERE activo = 1
        ORDER BY especialidad
    """).fetchall()
    conn.close()
    return especialidades

@app.route("/paciente")
@login_required
def paciente():
    if current_user.rol != "paciente":
        flash("No tenés permiso para ingresar a la vista paciente.")
        return redirect(url_for("login"))

    filtro_especialidad = request.args.get("especialidad", "")
    filtro_medico = request.args.get("id_medico", "")
    filtro_fecha = request.args.get("fecha", "")

    medicos_filtrados = obtener_medicos_por_disponibilidad(
        filtro_especialidad if filtro_especialidad else None,
        filtro_fecha if filtro_fecha else None
    )

    fechas_disponibles = obtener_fechas_disponibles(
        filtro_especialidad if filtro_especialidad else None,
        filtro_medico if filtro_medico else None
    )

    horarios_disponibles = obtener_horarios_filtrados(
        filtro_especialidad if filtro_especialidad else None,
        filtro_medico if filtro_medico else None,
        filtro_fecha if filtro_fecha else None
    )

    return render_template(
        "paciente.html",
        usuario=current_user,
        turnos=obtener_turnos_por_paciente(current_user.id),
        horarios_disponibles=horarios_disponibles,
        fechas_disponibles=fechas_disponibles,
        especialidades=obtener_especialidades(),
        medicos=medicos_filtrados,
        filtro_especialidad=filtro_especialidad,
        filtro_medico=filtro_medico,
        filtro_fecha=filtro_fecha
    )
@app.route("/paciente/cancelar_turno/<int:id_turno>", methods=["POST"])
@login_required
def paciente_cancelar_turno(id_turno):
    if current_user.rol != "paciente":
        flash("No tenés permiso para cancelar este turno.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    turno = cursor.execute("""
        SELECT * FROM turnos
        WHERE id = ? AND id_paciente = ?
    """, (id_turno, current_user.id)).fetchone()

    if turno:
        cursor.execute("""
            UPDATE horarios
            SET ocupado = 0
            WHERE id_horario = ?
        """, (turno["id_horario"],))

        cursor.execute("""
            UPDATE turnos
            SET estado = 'Cancelado'
            WHERE id = ?
        """, (id_turno,))

        conn.commit()
        flash("Turno cancelado con éxito. Si desea solicitar otro turno debe comunicarse con la administradora.")
    else:
        flash("No se pudo cancelar el turno seleccionado.")

    conn.close()
    return redirect(url_for("paciente"))

@app.route("/paciente/sacar_turno", methods=["POST"])
@login_required
def paciente_sacar_turno():
    if current_user.rol != "paciente":
        flash("No tenés permiso para solicitar turnos.")
        return redirect(url_for("login"))

    id_horario = request.form.get("id_horario")

    if not id_horario:
        flash("No se seleccionó un horario válido.")
        return redirect(url_for("paciente"))

    conn = get_conn()
    cursor = conn.cursor()

    # Verificar que el horario existe y está libre
    horario = cursor.execute("""
        SELECT horarios.*, medicos.nombre AS medico_nombre, medicos.apellido AS medico_apellido
        FROM horarios
        INNER JOIN medicos ON horarios.id_medico = medicos.id_medico
        WHERE horarios.id_horario = ? AND horarios.ocupado = 0
    """, (id_horario,)).fetchone()

    if not horario:
        conn.close()
        flash("El turno ya no está disponible. Intentá con otro.")
        return redirect(url_for("paciente"))

    # Verificar que el paciente no tenga ya un turno confirmado con ese médico en esa fecha
    turno_existente = cursor.execute("""
        SELECT * FROM turnos
        WHERE id_paciente = ? AND id_medico = ? AND fecha = ? AND estado = 'Confirmado'
    """, (current_user.id, horario["id_medico"], horario["fecha"])).fetchone()

    if turno_existente:
        conn.close()
        flash("Ya tenés un turno confirmado con ese médico en esa fecha.")
        return redirect(url_for("paciente"))

    paciente = cursor.execute("""
        SELECT * FROM usuarios WHERE id_usuario = ?
    """, (current_user.id,)).fetchone()

    nombre_paciente = f"{paciente['nombre']} {paciente['apellido']}"

    cursor.execute("""
        INSERT INTO turnos
        (id_paciente, id_horario, id_medico, paciente, especialidad, fecha, hora, estado, llamado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Confirmado', 0)
    """, (
        current_user.id,
        id_horario,
        horario["id_medico"],
        nombre_paciente,
        horario["especialidad"],
        horario["fecha"],
        horario["hora"]
    ))

    cursor.execute("""
        UPDATE horarios SET ocupado = 1 WHERE id_horario = ?
    """, (id_horario,))

    conn.commit()
    conn.close()

    flash(f"Turno solicitado correctamente para el {horario['fecha']} a las {horario['hora']} con el Dr/a {horario['medico_apellido']}.")
    return redirect(url_for("paciente"))

@app.route("/medico")
@login_required
def medico():
    if current_user.rol != "medico":
        flash("No tenés permiso para ingresar a la vista médica.")
        return redirect(url_for("login"))

    medico_db = obtener_medico_por_email(current_user.email)

    if not medico_db:
        flash("No hay médico asociado a este usuario.")
        return redirect(url_for("login"))

    filtro_fecha = request.args.get("fecha", "")

    return render_template(
        "medico.html",
        usuario=current_user,
        medico=medico_db,
        turnos=obtener_turnos_por_medico(
            medico_db["id_medico"],
            filtro_fecha if filtro_fecha else None
        ),
        filtro_fecha=filtro_fecha
    )

@app.route("/medico/llamado/<int:id_turno>", methods=["POST"])
@login_required
def medico_llamado(id_turno):
    if current_user.rol != "medico":
        flash("No tenés permiso para modificar la agenda médica.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    turno = cursor.execute("""
        SELECT llamado
        FROM turnos
        WHERE id = ?
    """, (id_turno,)).fetchone()

    if turno:
        nuevo_estado = 0 if turno["llamado"] == 1 else 1

        cursor.execute("""
            UPDATE turnos
            SET llamado = ?
            WHERE id = ?
        """, (nuevo_estado, id_turno))

        conn.commit()
        flash("Estado del paciente actualizado.")
    else:
        flash("Turno no encontrado.")

    conn.close()
    return redirect(url_for("medico"))


@app.route("/medico/perfil", methods=["GET", "POST"])
@login_required
def perfil_medico():

    if current_user.rol != "medico":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    usuario = obtener_usuario_por_id(current_user.id)
    medico = obtener_medico_por_email(current_user.email)

    if request.method == "POST":

        email_nuevo = request.form["email"].strip().lower()
        nombre_foto = medico["foto"]
    foto_archivo = request.files.get("foto")

    if foto_archivo and foto_archivo.filename != "":
        if not archivo_permitido(foto_archivo.filename):
            flash("Formato de imagen no permitido. Usá PNG, JPG, JPEG o WEBP.")
            return redirect(url_for("perfil_medico"))

        nombre_seguro = secure_filename(foto_archivo.filename)
        nombre_foto = f"{email_nuevo.replace('@', '_').replace('.', '_')}_{nombre_seguro}"
        ruta_foto = os.path.join(app.config["UPLOAD_FOLDER"], nombre_foto)
        foto_archivo.save(ruta_foto)

        actualizar_usuario(
            current_user.id,
            request.form["nombre"],
            request.form["apellido"],
            "",
            request.form["telefono"],
            email_nuevo,
            None
        )

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE medicos
            SET
                nombre = ?,
                apellido = ?,
                telefono = ?,
                email = ?,
                foto = ?
            WHERE id_medico = ?
        """, (
            request.form["nombre"],
            request.form["apellido"],
            request.form["telefono"],
            email_nuevo,
            nombre_foto,
            medico["id_medico"]
        ))

        conn.commit()
        conn.close()

        password_actual = request.form["password_actual"]
        nueva_password = request.form["nueva_password"]
        confirmar_password = request.form["confirmar_password"]

        if nueva_password:

            if not check_password_hash(
                usuario["password"],
                password_actual
            ):
                flash("La contraseña actual es incorrecta.")
                return redirect(url_for("perfil_medico"))

            if nueva_password != confirmar_password:
                flash("Las contraseñas nuevas no coinciden.")
                return redirect(url_for("perfil_medico"))

            cambiar_password_usuario(
                current_user.id,
                nueva_password
            )

        flash("Perfil actualizado correctamente.")
        return redirect(url_for("perfil_medico"))

    return render_template(
        "perfil_medico.html",
        usuario=usuario,
        medico=medico
    )


@app.route("/paciente/perfil", methods=["GET", "POST"])
@login_required
def perfil_paciente():

    if current_user.rol != "paciente":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    usuario = obtener_usuario_por_id(
        int(current_user.id)
    )

    if request.method == "POST":

        actualizar_usuario(
            int(current_user.id),
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"],
            request.form["email"].strip().lower(),
            request.form.get("fecha_nacimiento")
        )

        password_actual = request.form["password_actual"]
        nueva_password = request.form["nueva_password"]
        confirmar_password = request.form["confirmar_password"]

        if nueva_password:

            if not check_password_hash(
                usuario["password"],
                password_actual
            ):
                flash("La contraseña actual es incorrecta.")
                return redirect(url_for("perfil_paciente"))

            if nueva_password != confirmar_password:
                flash("Las contraseñas nuevas no coinciden.")
                return redirect(url_for("perfil_paciente"))

            cambiar_password_usuario(
                int(current_user.id),
                nueva_password
            )

        flash("Perfil actualizado correctamente.")
        return redirect(url_for("perfil_paciente"))

    return render_template(
        "perfil_paciente.html",
        usuario=usuario
    )
@app.route("/generar_horarios", methods=["POST"])
@login_required
def generar_horarios_route():

    if current_user.rol != "admin":
        flash("No tenés permiso para generar horarios.")
        return redirect(url_for("login"))

    id_medico = request.form["id_medico"]
    fecha = request.form["fecha"]
    hora_inicio = request.form["hora_inicio"]
    hora_fin = request.form["hora_fin"]
    frecuencia = request.form["frecuencia"]

    cantidad, mensaje = generar_horarios_automaticos(
        id_medico,
        fecha,
        hora_inicio,
        hora_fin,
        frecuencia
    )

    if cantidad > 0:
        flash(f"{mensaje} Se generaron {cantidad} turnos disponibles.")
    else:
        flash(mensaje)

    return redirect(url_for("admin") + "#agenda-disponible")


@app.route("/admin/desactivar_medico/<int:id_medico>", methods=["POST"])
@login_required
def desactivar_medico(id_medico):

    if current_user.rol != "admin":
        flash("No tenés permiso para realizar esta acción.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    medico = cursor.execute("""
        SELECT *
        FROM medicos
        WHERE id_medico = ?
    """, (id_medico,)).fetchone()

    if not medico:
        conn.close()
        flash("Médico no encontrado.")
        return redirect(url_for("admin"))

    cursor.execute("""
        UPDATE medicos
        SET activo = 0
        WHERE id_medico = ?
    """, (id_medico,))

    cursor.execute("""
        UPDATE horarios
        SET ocupado = 1
        WHERE id_medico = ?
        AND ocupado = 0
    """, (id_medico,))

    conn.commit()
    conn.close()

    flash("Médico desactivado correctamente. Ya no aparecerá para cargar ni asignar nuevos turnos.")
    return redirect(url_for("admin") + "#medicos")

@app.route("/admin/medicos")
@login_required
def admin_medicos():
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    busqueda = request.args.get("busqueda", "")
    especialidad = request.args.get("especialidad", "")
    estado = request.args.get("estado", "activos")

    return render_template(
        "admin_medicos.html",
        medicos=obtener_medicos(
            busqueda if busqueda else None,
            especialidad if especialidad else None,
            estado
        ),
        especialidades=obtener_especialidades(),
        busqueda=busqueda,
        filtro_especialidad=especialidad,
        filtro_estado=estado
    )
@app.route("/admin/medicos/editar/<int:id_medico>", methods=["POST"])
@login_required
def editar_medico(id_medico):
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    nombre = request.form["nombre"]
    apellido = request.form["apellido"]
    especialidad = request.form["especialidad"]
    email = request.form["email"].strip().lower()
    telefono = request.form["telefono"]

    conn = get_conn()
    cursor = conn.cursor()

    medico = cursor.execute("""
        SELECT *
        FROM medicos
        WHERE id_medico = ?
    """, (id_medico,)).fetchone()

    if not medico:
        conn.close()
        flash("Médico no encontrado.")
        return redirect(url_for("admin_medicos"))

    nombre_foto = medico["foto"]

    foto_archivo = request.files.get("foto")

    if foto_archivo and foto_archivo.filename != "":
        if not archivo_permitido(foto_archivo.filename):
            conn.close()
            flash("Formato de imagen no permitido. Usá PNG, JPG, JPEG o WEBP.")
            return redirect(url_for("admin_medicos"))

        nombre_seguro = secure_filename(foto_archivo.filename)
        nombre_foto = f"{email.replace('@', '_').replace('.', '_')}_{nombre_seguro}"
        ruta_foto = os.path.join(app.config["UPLOAD_FOLDER"], nombre_foto)
        foto_archivo.save(ruta_foto)

    try:
        cursor.execute("""
            UPDATE medicos
            SET
                nombre = ?,
                apellido = ?,
                especialidad = ?,
                email = ?,
                telefono = ?,
                foto = ?
            WHERE id_medico = ?
        """, (
            nombre,
            apellido,
            especialidad,
            email,
            telefono,
            nombre_foto,
            id_medico
        ))

        cursor.execute("""
            UPDATE usuarios
            SET
                nombre = ?,
                apellido = ?,
                telefono = ?,
                email = ?
            WHERE email = ?
            AND rol = 'medico'
        """, (
            nombre,
            apellido,
            telefono,
            email,
            medico["email"]
        ))

        conn.commit()
        flash("Datos del médico actualizados correctamente.")

    except Exception:
        flash("No se pudo actualizar el médico. Verificá que el correo no esté repetido.")

    conn.close()
    return redirect(url_for("admin_medicos"))
@app.route("/admin/activar_medico/<int:id_medico>", methods=["POST"])
@login_required
def activar_medico(id_medico):

    if current_user.rol != "admin":
        flash("No tenés permiso para realizar esta acción.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    medico = cursor.execute("""
        SELECT *
        FROM medicos
        WHERE id_medico = ?
    """, (id_medico,)).fetchone()

    if not medico:
        conn.close()
        flash("Médico no encontrado.")
        return redirect(url_for("admin_medicos"))

    cursor.execute("""
        UPDATE medicos
        SET activo = 1
        WHERE id_medico = ?
    """, (id_medico,))

    conn.commit()
    conn.close()

    flash("Médico activado correctamente. Ya puede volver a recibir horarios y turnos.")
    return redirect(url_for("admin_medicos"))

@app.route("/admin/agenda_disponible")
@login_required
def admin_agenda_disponible():
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    filtro_especialidad = request.args.get("especialidad", "")
    filtro_medico = request.args.get("id_medico", "")
    filtro_fecha = request.args.get("fecha", "")

    medicos_filtrados = obtener_medicos(
        especialidad=filtro_especialidad if filtro_especialidad else None
    )

    fechas_disponibles = obtener_fechas_disponibles(
        filtro_especialidad if filtro_especialidad else None,
        filtro_medico if filtro_medico else None
    )

    horarios = obtener_horarios_filtrados(
        filtro_especialidad if filtro_especialidad else None,
        filtro_medico if filtro_medico else None,
        filtro_fecha if filtro_fecha else None
    )

    return render_template(
        "agenda_disponible.html",
        horarios=horarios,
        fechas_disponibles=fechas_disponibles,
        medicos=medicos_filtrados,
        especialidades=obtener_especialidades(),
        filtro_especialidad=filtro_especialidad,
        filtro_medico=filtro_medico,
        filtro_fecha=filtro_fecha
    )
@app.route("/admin/pacientes")
@login_required
def admin_pacientes():
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    busqueda = request.args.get("busqueda", "")
    estado = request.args.get("estado", "activos")

    pacientes = obtener_pacientes_admin(
        busqueda if busqueda else None,
        estado
    )

    return render_template(
        "admin_pacientes.html",
        pacientes=pacientes,
        busqueda=busqueda,
        filtro_estado=estado,
        calcular_edad=calcular_edad
    )


@app.route("/admin/agregar_paciente", methods=["POST"])
@login_required
def admin_agregar_paciente():
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    try:
        registrar_paciente(
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"],
            request.form["email"],
            request.form["password"],
            request.form.get("fecha_nacimiento")
        )

        flash("Paciente agregado correctamente. Ya puede iniciar sesión con su email y contraseña.")

    except Exception as e:
        flash(f"Error: {str(e)}")

    return redirect(url_for("admin_pacientes"))


@app.route("/admin/pacientes/editar/<int:id_paciente>", methods=["POST"])
@login_required
def admin_editar_paciente(id_paciente):
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE usuarios
            SET
                nombre = ?,
                apellido = ?,
                dni = ?,
                telefono = ?,
                email = ?,
                fecha_nacimiento = ?
            WHERE id_usuario = ?
            AND rol = 'paciente'
        """, (
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"],
            request.form["email"].strip().lower(),
            request.form.get("fecha_nacimiento"),
            id_paciente
        ))

        conn.commit()
        flash("Paciente actualizado correctamente.")

    except Exception:
        flash("No se pudo actualizar el paciente. Verificá que el correo no esté repetido.")

    conn.close()
    return redirect(url_for("admin_pacientes"))


@app.route("/admin/pacientes/desactivar/<int:id_paciente>", methods=["POST"])
@login_required
def admin_desactivar_paciente(id_paciente):
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET activo = 0
        WHERE id_usuario = ?
        AND rol = 'paciente'
    """, (id_paciente,))

    conn.commit()
    conn.close()

    flash("Paciente desactivado correctamente.")
    return redirect(url_for("admin_pacientes"))


@app.route("/admin/pacientes/activar/<int:id_paciente>", methods=["POST"])
@login_required
def admin_activar_paciente(id_paciente):
    if current_user.rol != "admin":
        flash("No tenés permiso.")
        return redirect(url_for("login"))

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET activo = 1
        WHERE id_usuario = ?
        AND rol = 'paciente'
    """, (id_paciente,))

    conn.commit()
    conn.close()

    flash("Paciente activado correctamente.")
    return redirect(url_for("admin_pacientes"))

if __name__ == "__main__":
    app.run(debug=True)