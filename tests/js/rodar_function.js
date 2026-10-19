// Executa uma Function gerada com `context` falso e relógio fixo; imprime as chamadas.
// Uso: node rodar_function.js <arquivo.js> <instante ISO>
const fs = require("fs");
const FIXO = Date.parse(process.argv[3]);
const RealDate = Date;
class DataFixa extends RealDate {
  constructor(...a) { if (a.length === 0) super(FIXO); else super(...a); }
  static now() { return FIXO; }
}
global.Date = DataFixa;
const chamadas = [];
function colecao(nome) {
  return {
    count: async (q) => { chamadas.push(["count", nome, q]); return 7; },
    aggregate: (p) => ({
      toArray: async () => {
        chamadas.push(["aggregate", nome, p]);
        // relógio do servidor: 1 s depois do relógio da Function
        return p[1] && p[1].$project && p[1].$project.t ? [{ t: new RealDate(FIXO + 1000) }] : [];
      },
    }),
    find: (q) => ({ toArray: async () => { chamadas.push(["find", nome, q]); return [{ _id: "a" }, { _id: "b" }]; } }),
    deleteMany: async (q) => { chamadas.push(["deleteMany", nome, q]); return { deletedCount: 2 }; },
    insertOne: async (d) => { chamadas.push(["insertOne", nome, d]); return {}; },
  };
}
global.context = { services: { get: () => ({ db: (b) => ({ collection: (c) => colecao(`${b}.${c}`) }) }) } };
eval(fs.readFileSync(process.argv[2], "utf8"));
exports().then((r) => console.log(JSON.stringify({ r, chamadas })));
