// Executa uma Function gerada contra um MongoDB de verdade, pelo mongosh (sem App Services).
// O `context` só troca o serviço do App Services por uma conexão do mongosh; o código da
// Function é exatamente o arquivo versionado em atlas-trigger/functions/.
//
// Uso (a URI vai por variável de ambiente, nunca na linha de comando):
//   FROTA_FN_URI=<uri> FROTA_FN_DB=<banco *_test> FROTA_FN=<arquivo.js> \
//     mongosh --nodb --quiet --file tests/js/rodar_function_mongosh.js
// Imprime o retorno da Function em EJSON relaxado.
const fs = require("fs");

const nomeDb = process.env.FROTA_FN_DB || "";
if (!/_test$/.test(nomeDb)) throw new Error("recusado: a Function só roda aqui em banco *_test");
const alvo = new Mongo(process.env.FROTA_FN_URI).getDB(nomeDb);

function colecao(nome) {
  const c = alvo.getCollection(nome);
  return {
    count: async (q) => await c.countDocuments(q),
    aggregate: (p) => ({
      toArray: async () => {
        const cursor = await c.aggregate(p);
        return await cursor.toArray();
      },
    }),
    find: (q, proj) => ({
      toArray: async () => {
        const cursor = await c.find(q, proj);
        return await cursor.toArray();
      },
    }),
    deleteMany: async (q) => await c.deleteMany(q),
    insertOne: async (d) => await c.insertOne(d),
  };
}

// a Function chama context.services.get("mongodb-atlas").db(BANCO): o banco vira o *_test
globalThis.context = { services: { get: () => ({ db: () => ({ collection: colecao }) }) } };

const funcao = new Function("context",
  "let exports;\n" + fs.readFileSync(process.env.FROTA_FN, "utf8") + "\nreturn exports;");
// sem top-level await no --file: o mongosh espera a promise antes de sair
funcao(globalThis.context)().then(
  (r) => print(EJSON.stringify(r, { relaxed: true })),
  (e) => { printjson({ erro: String(e && e.message ? e.message : e) }); process.exitCode = 1; },
);
