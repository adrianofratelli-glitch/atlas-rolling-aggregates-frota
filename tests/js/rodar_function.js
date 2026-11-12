// Executa uma Function gerada com `context` falso e relógio fixo; imprime as chamadas.
// Uso: node rodar_function.js <arquivo.js> <instante ISO> [<janela JSON>]
// <janela JSON> = {"inicio", "fim", "dataRef"} que o servidor devolveria ao pipeline de janela
// (o cálculo real no MongoDB é conferido em tests/test_live_trigger.py).
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
        // pipeline de janela: o servidor devolve janela, dataRef e o relógio dele, 1 s depois
        // do relógio da Function
        if (p[1] && p[1].$unionWith) {
          const j = JSON.parse(process.argv[4]);
          return [{ t: new RealDate(FIXO + 1000), inicio: new RealDate(j.inicio),
                    fim: new RealDate(j.fim), dataRef: j.dataRef }];
        }
        return [];
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
