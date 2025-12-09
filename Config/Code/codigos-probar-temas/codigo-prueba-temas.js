// Función simple que suma dos números
function sumar(a, b) {
  return a + b;
}

// Clase Persona con constructor y método
class Persona {
  constructor(nombre, edad) {
    this.nombre = nombre;
    this.edad = edad;
  }

  saludar() {
    console.log(`Hola, soy ${this.nombre} y tengo ${this.edad} años.`);
  }
}

// Uso de la clase Persona
let persona = new Persona("Juan", 30);
persona.saludar();

// Condicional simple
let num1 = 5,
  num2 = 10;
if (num1 < num2) {
  console.log(`${num1} es menor que ${num2}`);
}

// Bucle for
for (let i = 0; i < 5; i++) {
  console.log(`Iteración ${i}`);
}

// Manejo de promesas (asíncrono)
function esperar(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pruebaAsync() {
  console.log("Esperando 1 segundo...");
  await esperar(1000);
  console.log("Hecho.");
}

pruebaAsync();
