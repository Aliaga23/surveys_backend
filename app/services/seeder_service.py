"""
Database Seeder Service
Servicio para poblar la base de datos con datos de prueba realistas
"""

import uuid
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from faker import Faker
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario
from app.models.survey import (
    PlantillaEncuesta, PreguntaEncuesta, OpcionEncuesta,
    CampanaEncuesta, Destinatario, EntregaEncuesta,
    RespuestaEncuesta, RespuestaPregunta
)
from app.models.catalogos import (
    Rol, TipoPregunta, Canal, EstadoCampana, EstadoEntrega
)
from app.models.administrador import Administrador

class DatabaseSeeder:
    def __init__(self, db: Session):
        self.db = db
        self.fake = Faker(['es_ES', 'es_MX', 'es_AR'])
        
        # Datos de prueba predefinidos
        self.empresas = [
            "TechCorp Solutions", "InnovateSoft", "Digital Dynamics", "CloudTech Pro",
            "DataFlow Systems", "SmartSolutions Inc", "FutureTech Labs", "CyberNet Corp",
            "Quantum Innovations", "PixelPerfect Studios", "CodeCrafters", "WebWizards",
            "MobileMasters", "AI Solutions Hub", "Blockchain Builders", "IoT Pioneers",
            "VR Visionaries", "AR Architects", "ML Masters", "DevOps Dynamics",
            "Security Shield", "Network Ninjas", "Database Dragons", "API Avengers",
            "Frontend Fighters", "Backend Battalion", "FullStack Force", "Agile Alliance",
            "Scrum Squad", "Lean Leaders"
        ]
        
        self.plantillas_data = [
            {
                "nombre": "Satisfacción del Cliente",
                "descripcion": "Encuesta para medir la satisfacción de nuestros clientes",
                "preguntas": [
                    {"texto": "¿Qué tan satisfecho está con nuestro servicio?", "tipo": "escala", "opciones": ["1", "2", "3", "4", "5"]},
                    {"texto": "¿Recomendaría nuestros servicios a otros?", "tipo": "opcion", "opciones": ["Definitivamente sí", "Probablemente sí", "No estoy seguro", "Probablemente no", "Definitivamente no"]},
                    {"texto": "¿Qué aspectos podríamos mejorar?", "tipo": "texto"},
                    {"texto": "¿Cuál es su edad?", "tipo": "numero"},
                    {"texto": "¿Con qué frecuencia utiliza nuestros servicios?", "tipo": "opcion", "opciones": ["Diariamente", "Semanalmente", "Mensualmente", "Ocasionalmente", "Primera vez"]}
                ]
            },
            {
                "nombre": "Experiencia de Usuario",
                "descripcion": "Evaluación de la experiencia de usuario en nuestra plataforma",
                "preguntas": [
                    {"texto": "¿Qué tan fácil es navegar por nuestra plataforma?", "tipo": "escala", "opciones": ["1", "2", "3", "4", "5"]},
                    {"texto": "¿Encuentra la información que busca fácilmente?", "tipo": "opcion", "opciones": ["Siempre", "Frecuentemente", "A veces", "Raramente", "Nunca"]},
                    {"texto": "¿Qué funcionalidad le gustaría que agregáramos?", "tipo": "texto"},
                    {"texto": "¿Cuánto tiempo pasa en promedio en nuestra plataforma?", "tipo": "numero"},
                    {"texto": "¿Prefiere usar nuestra aplicación móvil o web?", "tipo": "opcion", "opciones": ["Aplicación móvil", "Sitio web", "Ambos por igual", "No tengo preferencia"]}
                ]
            },
            {
                "nombre": "Calidad del Producto",
                "descripcion": "Evaluación de la calidad de nuestros productos",
                "preguntas": [
                    {"texto": "¿Qué tan satisfecho está con la calidad del producto?", "tipo": "escala", "opciones": ["1", "2", "3", "4", "5"]},
                    {"texto": "¿El producto cumple con sus expectativas?", "tipo": "opcion", "opciones": ["Excede las expectativas", "Cumple las expectativas", "Cumple parcialmente", "No cumple las expectativas"]},
                    {"texto": "¿Qué características le gustaría que mejoráramos?", "tipo": "texto"},
                    {"texto": "¿Cuánto tiempo ha estado usando nuestro producto?", "tipo": "numero"},
                    {"texto": "¿Qué tipo de soporte técnico ha necesitado?", "tipo": "opcion", "opciones": ["Ninguno", "Básico", "Intermedio", "Avanzado", "Crítico"]}
                ]
            },
            {
                "nombre": "Atención al Cliente",
                "descripcion": "Evaluación de nuestro servicio de atención al cliente",
                "preguntas": [
                    {"texto": "¿Qué tan satisfecho está con la atención recibida?", "tipo": "escala", "opciones": ["1", "2", "3", "4", "5"]},
                    {"texto": "¿Cuánto tiempo tardó en recibir respuesta?", "tipo": "opcion", "opciones": ["Inmediatamente", "Menos de 1 hora", "1-4 horas", "4-24 horas", "Más de 24 horas"]},
                    {"texto": "¿Qué sugerencias tiene para mejorar el servicio?", "tipo": "texto"},
                    {"texto": "¿Cuántas veces ha contactado a soporte este mes?", "tipo": "numero"},
                    {"texto": "¿Qué canal de comunicación prefiere?", "tipo": "opcion", "opciones": ["Teléfono", "Email", "Chat en vivo", "WhatsApp", "Redes sociales"]}
                ]
            },
            {
                "nombre": "Preferencias de Marketing",
                "descripcion": "Encuesta sobre preferencias de marketing y comunicación",
                "preguntas": [
                    {"texto": "¿Qué tan efectivas encuentra nuestras campañas de marketing?", "tipo": "escala", "opciones": ["1", "2", "3", "4", "5"]},
                    {"texto": "¿Qué tipo de contenido le interesa más?", "tipo": "opcion", "opciones": ["Tutoriales", "Casos de éxito", "Novedades", "Ofertas especiales", "Contenido educativo"]},
                    {"texto": "¿Qué temas le gustaría que cubriéramos en nuestras comunicaciones?", "tipo": "texto"},
                    {"texto": "¿Cuántos emails de marketing abre por semana?", "tipo": "numero"},
                    {"texto": "¿En qué momento del día prefiere recibir nuestras comunicaciones?", "tipo": "opcion", "opciones": ["Mañana", "Mediodía", "Tarde", "Noche", "No tengo preferencia"]}
                ]
            }
        ]

    def seed_catalogos(self):
        """Crear datos de catálogos necesarios"""
        try:
            # Roles
            roles = [
                {"id": 1, "nombre": "admin"},
                {"id": 2, "nombre": "empresa"},
                {"id": 3, "nombre": "operator"}
            ]
            
            for rol_data in roles:
                # Verificar por ID y por nombre
                rol = self.db.query(Rol).filter(
                    (Rol.id == rol_data["id"]) | (Rol.nombre == rol_data["nombre"])
                ).first()
                if not rol:
                    rol = Rol(**rol_data)
                    self.db.add(rol)
            
            # Tipos de pregunta
            tipos_pregunta = [
                {"id": 1, "nombre": "texto"},
                {"id": 2, "nombre": "numero"},
                {"id": 3, "nombre": "opcion"},
                {"id": 4, "nombre": "escala"}
            ]
            
            for tipo_data in tipos_pregunta:
                tipo = self.db.query(TipoPregunta).filter(
                    (TipoPregunta.id == tipo_data["id"]) | (TipoPregunta.nombre == tipo_data["nombre"])
                ).first()
                if not tipo:
                    tipo = TipoPregunta(**tipo_data)
                    self.db.add(tipo)
            
            # Canales
            canales = [
                {"id": 1, "nombre": "email"},
                {"id": 2, "nombre": "whatsapp"},
                {"id": 3, "nombre": "sms"},
                {"id": 4, "nombre": "vapi"}
            ]
            
            for canal_data in canales:
                canal = self.db.query(Canal).filter(
                    (Canal.id == canal_data["id"]) | (Canal.nombre == canal_data["nombre"])
                ).first()
                if not canal:
                    canal = Canal(**canal_data)
                    self.db.add(canal)
            
            # Estados de campaña
            estados_campana = [
                {"id": 1, "nombre": "borrador"},
                {"id": 2, "nombre": "programada"},
                {"id": 3, "nombre": "en_proceso"},
                {"id": 4, "nombre": "completada"},
                {"id": 5, "nombre": "cancelada"}
            ]
            
            for estado_data in estados_campana:
                estado = self.db.query(EstadoCampana).filter(
                    (EstadoCampana.id == estado_data["id"]) | (EstadoCampana.nombre == estado_data["nombre"])
                ).first()
                if not estado:
                    estado = EstadoCampana(**estado_data)
                    self.db.add(estado)
            
            # Estados de entrega
            estados_entrega = [
                {"id": 1, "nombre": "pendiente"},
                {"id": 2, "nombre": "enviada"},
                {"id": 3, "nombre": "respondida"},
                {"id": 4, "nombre": "fallida"},
                {"id": 5, "nombre": "cancelada"}
            ]
            
            for estado_data in estados_entrega:
                estado = self.db.query(EstadoEntrega).filter(
                    (EstadoEntrega.id == estado_data["id"]) | (EstadoEntrega.nombre == estado_data["nombre"])
                ).first()
                if not estado:
                    estado = EstadoEntrega(**estado_data)
                    self.db.add(estado)
            
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise Exception(f"Error creando catálogos: {str(e)}")

    def seed_suscriptores(self, cantidad: int = 30) -> List[Suscriptor]:
        """Crear suscriptores (empresas)"""
        suscriptores = []
        for i in range(cantidad):
            empresa_nombre = self.empresas[i] if i < len(self.empresas) else f"Empresa {i+1}"
            
            suscriptor = Suscriptor(
                id=uuid.uuid4(),
                nombre=empresa_nombre,
                email=f"suscritor@{empresa_nombre.lower().replace(' ', '').replace('.', '').replace(',', '')}.com",
                telefono=f"+52{random.randint(1000000000, 9999999999)}",
                password_hash=hash_password("password123"),
                rol_id=3,  # empresa
                estado="activo",
                stripe_customer_id=f"cus_{self.fake.uuid4()[:14]}"
            )
            
            self.db.add(suscriptor)
            suscriptores.append(suscriptor)
        
        self.db.commit()
        return suscriptores

    def seed_operadores(self, suscriptores: List[Suscriptor]) -> List[CuentaUsuario]:
        """Crear 4 operadores por suscriptor"""
        operadores = []
        for suscriptor in suscriptores:
            for i in range(4):
                operador = CuentaUsuario(
                    id=uuid.uuid4(),
                    suscriptor_id=suscriptor.id,
                    email=f"operador{i+1}@{suscriptor.nombre.lower().replace(' ', '').replace('.', '').replace(',', '')}.com",
                    password_hash=hash_password("password123"),
                    nombre_completo=f"{self.fake.first_name()} {self.fake.last_name()}",
                    rol_id=2,  # operator
                    activo=True
                )
                
                self.db.add(operador)
                operadores.append(operador)
        
        self.db.commit()
        return operadores

    def seed_plantillas(self, suscriptores: List[Suscriptor]) -> List[PlantillaEncuesta]:
        """Crear 5 plantillas por suscriptor"""
        plantillas = []
        for suscriptor in suscriptores:
            for i, plantilla_data in enumerate(self.plantillas_data):
                plantilla = PlantillaEncuesta(
                    id=uuid.uuid4(),
                    suscriptor_id=suscriptor.id,
                    nombre=f"{plantilla_data['nombre']} - {suscriptor.nombre}",
                    descripcion=plantilla_data['descripcion'],
                    activo=True
                )
                
                self.db.add(plantilla)
                self.db.flush()  # Para obtener el ID de la plantilla
                
                # Crear preguntas para esta plantilla
                for j, pregunta_data in enumerate(plantilla_data['preguntas']):
                    tipo_id = {
                        'texto': 1,
                        'numero': 2,
                        'opcion': 3,
                        'escala': 4
                    }[pregunta_data['tipo']]
                    
                    pregunta = PreguntaEncuesta(
                        id=uuid.uuid4(),
                        plantilla_id=plantilla.id,
                        orden=j + 1,
                        texto=pregunta_data['texto'],
                        tipo_pregunta_id=tipo_id,
                        obligatorio=True
                    )
                    
                    self.db.add(pregunta)
                    self.db.flush()
                    
                    # Crear opciones si es necesario
                    if 'opciones' in pregunta_data:
                        for k, opcion_texto in enumerate(pregunta_data['opciones']):
                            opcion = OpcionEncuesta(
                                id=uuid.uuid4(),
                                pregunta_id=pregunta.id,
                                texto=opcion_texto,
                                valor=str(k + 1)
                            )
                            self.db.add(opcion)
                
                plantillas.append(plantilla)
        
        self.db.commit()
        return plantillas

    def seed_destinatarios(self, suscriptores: List[Suscriptor]) -> List[Destinatario]:
        """Crear destinatarios para las encuestas"""
        destinatarios = []
        for suscriptor in suscriptores:
            # Crear 20 destinatarios por suscriptor
            for i in range(20):
                destinatario = Destinatario(
                    id=uuid.uuid4(),
                    suscriptor_id=suscriptor.id,
                    nombre=f"{self.fake.first_name()} {self.fake.last_name()}",
                    telefono=f"+52{random.randint(1000000000, 9999999999)}",
                    email=self.fake.email()
                )
                
                self.db.add(destinatario)
                destinatarios.append(destinatario)
        
        self.db.commit()
        return destinatarios

    def seed_campanas(self, suscriptores: List[Suscriptor], plantillas: List[PlantillaEncuesta]) -> List[CampanaEncuesta]:
        """Crear campañas de encuestas"""
        campanas = []
        plantillas_por_suscriptor = {}
        
        # Agrupar plantillas por suscriptor
        for plantilla in plantillas:
            if plantilla.suscriptor_id not in plantillas_por_suscriptor:
                plantillas_por_suscriptor[plantilla.suscriptor_id] = []
            plantillas_por_suscriptor[plantilla.suscriptor_id].append(plantilla)
        
        for suscriptor in suscriptores:
            if suscriptor.id in plantillas_por_suscriptor:
                for plantilla in plantillas_por_suscriptor[suscriptor.id]:
                    # Crear 2 campañas por plantilla
                    for i in range(2):
                        campana = CampanaEncuesta(
                            id=uuid.uuid4(),
                            suscriptor_id=suscriptor.id,
                            plantilla_id=plantilla.id,
                            nombre=f"Campaña {i+1} - {plantilla.nombre}",
                            canal_id=random.choice([1, 2, 3, 4]),  # email, whatsapp, sms, vapi
                            programada_en=datetime.now() - timedelta(days=random.randint(1, 30)),
                            estado_id=random.choice([3, 4])  # en_proceso o completada
                        )
                        
                        self.db.add(campana)
                        campanas.append(campana)
        
        self.db.commit()
        return campanas

    def seed_entregas_y_respuestas(self, campanas: List[CampanaEncuesta], destinatarios: List[Destinatario]) -> Dict[str, int]:
        """Crear entregas y respuestas realistas"""
        destinatarios_por_suscriptor = {}
        for destinatario in destinatarios:
            if destinatario.suscriptor_id not in destinatarios_por_suscriptor:
                destinatarios_por_suscriptor[destinatario.suscriptor_id] = []
            destinatarios_por_suscriptor[destinatario.suscriptor_id].append(destinatario)
        
        entregas_creadas = 0
        respuestas_creadas = 0
        
        for campana in campanas:
            # Obtener destinatarios del suscriptor de la campaña
            suscriptor_destinatarios = destinatarios_por_suscriptor.get(campana.suscriptor_id, [])
            
            if not suscriptor_destinatarios:
                continue
            
            # Crear entre 5 y 15 entregas por campaña
            num_entregas = random.randint(5, 15)
            
            for i in range(num_entregas):
                destinatario = random.choice(suscriptor_destinatarios)
                
                entrega = EntregaEncuesta(
                    id=uuid.uuid4(),
                    campana_id=campana.id,
                    destinatario_id=destinatario.id,
                    canal_id=campana.canal_id,
                    estado_id=random.choice([2, 3]),  # enviada o respondida
                    enviado_en=datetime.now() - timedelta(days=random.randint(1, 7)),
                    respondido_en=datetime.now() - timedelta(hours=random.randint(1, 24)) if random.random() > 0.3 else None
                )
                
                self.db.add(entrega)
                self.db.flush()
                entregas_creadas += 1
                
                # Si la entrega fue respondida, crear respuestas
                if entrega.respondido_en:
                    # Obtener preguntas de la plantilla
                    preguntas = self.db.query(PreguntaEncuesta).filter(
                        PreguntaEncuesta.plantilla_id == campana.plantilla_id
                    ).order_by(PreguntaEncuesta.orden).all()
                    
                    if preguntas:
                        respuesta = RespuestaEncuesta(
                            id=uuid.uuid4(),
                            entrega_id=entrega.id,
                            puntuacion=random.uniform(3.0, 5.0),
                            raw_payload={"source": "seeder", "timestamp": entrega.respondido_en.isoformat()}
                        )
                        
                        self.db.add(respuesta)
                        self.db.flush()
                        respuestas_creadas += 1
                        
                        # Crear respuestas para cada pregunta
                        for pregunta in preguntas:
                            respuesta_pregunta = self._crear_respuesta_pregunta_realista(
                                respuesta.id, pregunta
                            )
                            if respuesta_pregunta:
                                self.db.add(respuesta_pregunta)
        
        self.db.commit()
        return {"entregas": entregas_creadas, "respuestas": respuestas_creadas}

    def _crear_respuesta_pregunta_realista(self, respuesta_id: uuid.UUID, pregunta: PreguntaEncuesta) -> RespuestaPregunta:
        """Crear una respuesta realista para una pregunta específica"""
        opciones = self.db.query(OpcionEncuesta).filter(
            OpcionEncuesta.pregunta_id == pregunta.id
        ).all()
        
        if pregunta.tipo_pregunta_id == 1:  # texto
            respuestas_texto = [
                "Excelente servicio, muy satisfecho con la atención recibida.",
                "Bueno en general, pero hay aspectos que podrían mejorar.",
                "El producto cumple con lo esperado, lo recomendaría.",
                "Necesita mejoras en la interfaz de usuario.",
                "Muy buena experiencia, seguiré usando el servicio.",
                "Regular, esperaba más funcionalidades.",
                "Soporte técnico muy eficiente y amigable.",
                "La calidad del producto es superior a la competencia.",
                "Proceso de compra muy sencillo y rápido.",
                "Excelente relación calidad-precio."
            ]
            
            return RespuestaPregunta(
                id=uuid.uuid4(),
                respuesta_id=respuesta_id,
                pregunta_id=pregunta.id,
                texto=random.choice(respuestas_texto)
            )
        
        elif pregunta.tipo_pregunta_id == 2:  # numero
            return RespuestaPregunta(
                id=uuid.uuid4(),
                respuesta_id=respuesta_id,
                pregunta_id=pregunta.id,
                numero=random.randint(1, 100)
            )
        
        elif pregunta.tipo_pregunta_id == 3:  # opcion
            if opciones:
                opcion_elegida = random.choice(opciones)
                return RespuestaPregunta(
                    id=uuid.uuid4(),
                    respuesta_id=respuesta_id,
                    pregunta_id=pregunta.id,
                    opcion_id=opcion_elegida.id
                )
        
        elif pregunta.tipo_pregunta_id == 4:  # escala
            return RespuestaPregunta(
                id=uuid.uuid4(),
                respuesta_id=respuesta_id,
                pregunta_id=pregunta.id,
                numero=random.randint(3, 5)  # Tendencia positiva
            )
        
        return None

    def run(self) -> Dict[str, Any]:
        """Ejecutar todo el proceso de seeding"""
        try:
            # Verificar si ya se ejecutó el seeder
            if self.verificar_seeder_ejecutado():
                return {
                    "mensaje": "El seeder ya fue ejecutado anteriormente",
                    "suscriptores_existentes": self.db.query(Suscriptor).count(),
                    "operadores_existentes": self.db.query(CuentaUsuario).filter(CuentaUsuario.rol_id == 3).count(),
                    "plantillas_existentes": self.db.query(PlantillaEncuesta).count(),
                    "entregas_existentes": self.db.query(EntregaEncuesta).count()
                }
            
            # 1. Crear catálogos
            self.seed_catalogos()
            
            # 2. Crear suscriptores
            suscriptores = self.seed_suscriptores(30)
            
            # 3. Crear operadores
            operadores = self.seed_operadores(suscriptores)
            
            # 4. Crear plantillas
            plantillas = self.seed_plantillas(suscriptores)
            
            # 5. Crear destinatarios
            destinatarios = self.seed_destinatarios(suscriptores)
            
            # 6. Crear campañas
            campanas = self.seed_campanas(suscriptores, plantillas)
            
            # 7. Crear entregas y respuestas
            entregas_respuestas = self.seed_entregas_y_respuestas(campanas, destinatarios)
            
            return {
                "mensaje": "Seeding completado exitosamente",
                "suscriptores_creados": len(suscriptores),
                "operadores_creados": len(operadores),
                "plantillas_creadas": len(plantillas),
                "destinatarios_creados": len(destinatarios),
                "campanas_creadas": len(campanas),
                "entregas_creadas": entregas_respuestas["entregas"],
                "respuestas_creadas": entregas_respuestas["respuestas"]
            }
            
        except Exception as e:
            self.db.rollback()
            raise e

    def seed_basico(self) -> Dict[str, Any]:
        """Crea roles, un usuario admin y un suscriptor demo"""
        from app.models.suscriptor import Suscriptor
        from app.models.catalogos import Rol
        from app.core.security import hash_password
        import uuid

        # Crear roles si no existen
        roles = {
            "admin": 1,
            "empresa": 3,
            "operator": 2
        }

        for nombre, rol_id in roles.items():
            if not self.db.query(Rol).filter(Rol.nombre == nombre).first():
                self.db.add(Rol(id=rol_id, nombre=nombre))

        self.db.flush()

        # Crear admin
        admin_email = "admin@admin.com"
        if not self.db.query(Administrador).filter(Administrador.email == admin_email).first():
            admin = Administrador(
                id=uuid.uuid4(),
                email=admin_email,
                password_hash=hash_password("admin123"),
                rol_id=1,
                activo=True
            )
            self.db.add(admin)

        # Crear empresa demo
        demo_email = "demo@empresa.com"
        if not self.db.query(Suscriptor).filter(Suscriptor.email == demo_email).first():
            demo = Suscriptor(
                id=uuid.uuid4(),
                nombre="Empresa Demo",
                email=demo_email,
                telefono=self.fake.phone_number(),
                password_hash=hash_password("demo123"),
                rol_id=3,
                estado="activo",
                stripe_customer_id=f"cus_{self.fake.uuid4()[:14]}"
            )
            self.db.add(demo)

        self.db.commit()
        return {
            "roles_creados": list(roles.keys()),
            "admin_email": admin_email,
            "empresa_demo_email": demo_email
        }

    def verificar_seeder_ejecutado(self) -> bool:
        """Verifica si el seeder ya fue ejecutado"""
        try:
            # Verificar si ya hay suscriptores creados por el seeder
            suscriptores_count = self.db.query(Suscriptor).count()
            operadores_count = self.db.query(CuentaUsuario).filter(CuentaUsuario.rol_id == 3).count()
            
            # Si hay más de 25 suscriptores y más de 100 operadores, asumimos que ya se ejecutó
            return suscriptores_count >= 25 and operadores_count >= 100
        except Exception:
            return False
