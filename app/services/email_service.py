import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from typing import Optional
from fastapi import HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)

async def enviar_email(
    destinatario_email: str,
    destinatario_nombre: str,
    asunto: str,
    nombre_campana: str,
    nombre_empresa: str, 
    url_encuesta: str
) -> bool:
    """
    Envía un email al destinatario con el link de la encuesta usando SMTP de Google
    """
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = asunto
        message["From"] = f"{nombre_empresa} <{settings.SMTP_USERNAME}>"
        message["To"] = f"{destinatario_nombre} <{destinatario_email}>"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
            <h2 style="color: #333;">Hola {destinatario_nombre},</h2>
            
            <p>Te invitamos a participar en nuestra encuesta: <strong>{nombre_campana}</strong>.</p>
            
            <p>Tu opinión es muy importante para {nombre_empresa}. 
            La encuesta solo tomará unos minutos de tu tiempo.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{url_encuesta}" style="background-color: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Responder Encuesta
                </a>
            </div>
            
            <p>Si el botón no funciona, puedes copiar y pegar este enlace en tu navegador:</p>
            <p style="word-break: break-all; font-size: 12px;">{url_encuesta}</p>
            
            <p>El enlace estará activo por {settings.SURVEY_LINK_EXPIRY_DAYS} días.</p>
            
            <p style="color: #777; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px;">
                Este es un mensaje automático, por favor no respondas a este email.
            </p>
        </div>
        """
        
        text_content = f"""
        Hola {destinatario_nombre},
        
        Te invitamos a participar en nuestra encuesta: {nombre_campana}.
        
        Tu opinión es muy importante para {nombre_empresa}. La encuesta solo tomará unos minutos de tu tiempo.
        
        Para responder, visita: {url_encuesta}
        
        El enlace estará activo por {settings.SURVEY_LINK_EXPIRY_DAYS} días.
        
        Este es un mensaje automático, por favor no respondas a este email.
        """
        
        # Adjuntar las partes al mensaje
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        message.attach(part1)
        message.attach(part2)
        
        if settings.SMTP_PORT == 465:
            smtp = aiosmtplib.SMTP(
                hostname=settings.SMTP_SERVER, 
                port=settings.SMTP_PORT, 
                use_tls=True 
            )
            await smtp.connect()  
        else:
            smtp = aiosmtplib.SMTP(
                hostname=settings.SMTP_SERVER, 
                port=settings.SMTP_PORT,
                use_tls=False 
            )
            await smtp.connect()
            await smtp.starttls()  
        
        await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        await smtp.send_message(message)
        await smtp.quit()
        
        logger.info(f"Email enviado a {destinatario_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error enviando email: {str(e)}")
        return False


async def enviar_email_verificacion(
    destinatario_email: str,
    destinatario_nombre: str,
    url_verificacion: str
) -> bool:
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "Verifica tu cuenta en SurveySaaS"
        message["From"] = f"SurveySaaS <{settings.SMTP_USERNAME}>"
        message["To"] = f"{destinatario_nombre} <{destinatario_email}>"

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
            <h2 style="color: #333;">Hola {destinatario_nombre},</h2>

            <p>Gracias por registrarte en SurveySaaS. Por favor verifica tu correo haciendo clic en el siguiente botón:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{url_verificacion}" style="background-color: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Verificar mi cuenta
                </a>
            </div>

            <p>Si el botón no funciona, copia y pega este enlace en tu navegador:</p>
            <p style="word-break: break-all; font-size: 12px;">{url_verificacion}</p>

            <p>El enlace estará activo por 24 horas.</p>

            <p style="color: #777; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px;">
                Este es un mensaje automático, por favor no respondas a este email.
            </p>
        </div>
        """

        text_content = f"""
        Hola {destinatario_nombre},

        Gracias por registrarte en SurveySaaS. Por favor verifica tu correo visitando el siguiente enlace:

        {url_verificacion}

        El enlace estará activo por 24 horas.

        Este es un mensaje automático, por favor no respondas a este email.
        """

        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        message.attach(part1)
        message.attach(part2)

        smtp = aiosmtplib.SMTP(
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            use_tls=(settings.SMTP_PORT == 465)
        )
        await smtp.connect()
        if settings.SMTP_PORT != 465:
            await smtp.starttls()
        await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        await smtp.send_message(message)
        await smtp.quit()

        logger.info(f"Correo de verificación enviado a {destinatario_email}")
        return True

    except Exception as e:
        logger.error(f"Error enviando email de verificación: {str(e)}")
        return False
