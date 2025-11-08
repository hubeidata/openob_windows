from PIL import Image

# Ruta del archivo original
input_path = "ui\images\ob-logo.png"
output_path = "ui\images\ob-logo.ico"

# Cargar la imagen y convertirla a formato ICO
img = Image.open(input_path)
img.save(output_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

output_path