import os
import re
import uuid
from flask import Flask, request, jsonify, render_template, redirect, session, url_for
from database import get_connection, create_table
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave-secreta-dev-123")  # troque em produção por variável de ambiente

# --- CONFIGURAÇÕES DE UPLOAD ---
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- VALIDAÇÃO DE SENHA ---
def senha_valida(senha):
    """Retorna (True, None) se a senha for válida, ou (False, mensagem) caso contrário."""
    if len(senha) < 8:
        return False, "A senha deve ter no mínimo 8 caracteres."
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;\'`~/]', senha):
        return False, "A senha deve conter pelo menos um caractere especial."
    return True, None

# --- DECORADOR DE LOGIN ---
def login_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROTAS GERAIS ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "API de catálogo de filmes"}), 200

@app.route('/ping', methods=['GET'])
def ping():
    try:
        conn = get_connection()
        conn.close()
        return jsonify({"message": "pong! API Rodando!", "db": "SQLite conectado com sucesso!"}), 200
    except Exception as ex:
        return jsonify({"message": "Erro ao conectar ao banco", "erro": str(ex)}), 500

# --- FILMES ---

@app.route('/filmes', methods=['GET'])
@login_required
def listar_filmes():
    sql = "SELECT * FROM filmes"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        filmes = cursor.fetchall()
        conn.close()
        return render_template("index.html", filmes=filmes)
    except Exception as ex:
        print('erro: ', str(ex))
        return render_template("erro.html", erro="Erro ao listar filmes")

@app.route("/novo_filme", methods=["GET", "POST"])
@login_required
def novo_filme():
    if request.method == "POST":
        try:
            titulo = request.form["titulo"]
            genero = request.form["genero"]
            ano = request.form["ano"]
            file = request.files.get("url_capa")

            if file and allowed_file(file.filename):
                extensao = file.filename.rsplit('.', 1)[1].lower()
                nome_hash = f"{uuid.uuid4().hex}.{extensao}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_hash))
                url_capa = f"uploads/{nome_hash}"

                sql = "INSERT INTO filmes (titulo, genero, ano, url_capa) VALUES (?, ?, ?, ?)"
                params = [titulo, genero, ano, url_capa]

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()
                conn.close()
                return redirect(url_for("listar_filmes"))

            return render_template("erro.html", erro="Arquivo inválido ou não enviado")
        except Exception as ex:
            print('erro: ', str(ex))
            return render_template("erro.html", erro="Erro ao cadastrar filme")

    return render_template("novo_filme.html")

@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_filme(id):
    try:
        if request.method == "POST":
            titulo = request.form["titulo"]
            genero = request.form["genero"]
            ano = request.form["ano"]
            file = request.files.get("url_capa")

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT url_capa FROM filmes WHERE id = ?", [id])
            filme_atual = cursor.fetchone()

            url_capa = filme_atual['url_capa']

            if file and allowed_file(file.filename):
                extensao = file.filename.rsplit('.', 1)[1].lower()
                nome_hash = f"{uuid.uuid4().hex}.{extensao}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_hash))
                url_capa = f"uploads/{nome_hash}"

            sql_update = "UPDATE filmes SET titulo = ?, genero = ?, ano = ?, url_capa = ? WHERE id = ?"
            cursor.execute(sql_update, [titulo, genero, ano, url_capa, id])
            conn.commit()
            conn.close()
            return redirect(url_for("listar_filmes"))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM filmes WHERE id = ?", [id])
        filme = cursor.fetchone()
        conn.close()

        if filme is None:
            return redirect(url_for("listar_filmes"))
        return render_template("editar_filme.html", filme=filme)

    except Exception as ex:
        print('erro: ', str(ex))
        return render_template("erro.html", erro="Erro ao editar filme")

@app.route("/deletar/<int:id>", methods=["POST"])
@login_required
def deletar_filme(id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM filmes WHERE id = ?", [id])
        conn.commit()
        conn.close()
        return redirect(url_for("listar_filmes"))
    except Exception as ex:
        print('erro: ', str(ex))
        return render_template("erro.html", erro="Erro ao deletar filme")

# --- AUTENTICAÇÃO ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuario WHERE email = ?", [email])
            usuario = cursor.fetchone()
            conn.close()
        except Exception as ex:
            print('erro: ', str(ex))
            return render_template("login.html", erro="Erro ao consultar banco de dados")

        # Usuário não encontrado
        if usuario is None:
            return render_template("login.html", erro="E-mail não encontrado")

        # Senha incorreta
        if not check_password_hash(usuario["senha"], password):
            return render_template("login.html", erro="Senha incorreta")

        # Login bem-sucedido
        session["user"] = usuario["email"]
        return redirect(url_for("listar_filmes"))

    return render_template("login.html", erro=None)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# --- CADASTRO DE USUÁRIOS ---

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        email = request.form["email"].strip()
        senha = request.form["senha"]
        confirmar_senha = request.form["confirmar_senha"]

        # Validações básicas
        if not nome or not email or not senha:
            return render_template("cadastro.html", erro="Todos os campos são obrigatórios")

        if senha != confirmar_senha:
            return render_template("cadastro.html", erro="As senhas não coincidem")

        valida, mensagem_erro = senha_valida(senha)
        if not valida:
            return render_template("cadastro.html", erro=mensagem_erro)

        # Criptografa a senha
        senha_hash = generate_password_hash(senha)

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Verifica se e-mail já está cadastrado
            cursor.execute("SELECT id FROM usuario WHERE email = ?", [email])
            if cursor.fetchone():
                conn.close()
                return render_template("cadastro.html", erro="E-mail já cadastrado")

            cursor.execute(
                "INSERT INTO usuario (nome, email, senha) VALUES (?, ?, ?)",
                [nome, email, senha_hash]
            )
            conn.commit()
            conn.close()
            return redirect(url_for("login"))

        except Exception as ex:
            print('erro: ', str(ex))
            return render_template("cadastro.html", erro="Erro ao cadastrar usuário")

    return render_template("cadastro.html", erro=None)


# Cria as tabelas ao iniciar a aplicação
create_table()

if __name__ == '__main__':
    app.run(debug=True)