hola es prueba
para hacer correr:
docker start pg_diagramador_dev

cd backend
venv\Scripts\activate
uvicorn app.main:app --reload

cd frontend
npm run dev

