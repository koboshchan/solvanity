// npm install @solana/web3.js@1
// Build only. No wallet secrets, RPC calls, signing, or sending.
// Usage: node examples/create-account-with-seed.mjs result.json SPACE RENT_LAMPORTS
import fs from "node:fs";
import { PublicKey, SystemProgram, Transaction } from "@solana/web3.js";

const [filename, spaceArg, rentArg] = process.argv.slice(2);
if (!filename || !spaceArg || !rentArg) {
  throw new Error("Usage: node create-account-with-seed.mjs result.json SPACE RENT_LAMPORTS");
}
const result = JSON.parse(fs.readFileSync(filename, "utf8"));
// result.json must contain a single hit object, not a JSON Lines log.
const { base, owner, seed, address } = result;
if (typeof seed !== "string" || Buffer.byteLength(seed, "utf8") > 32) {
  throw new Error("seed must be a UTF-8 string of at most 32 bytes");
}
const basePubkey = new PublicKey(base);
const programId = new PublicKey(owner);
const newAccountPubkey = await PublicKey.createWithSeed(basePubkey, seed, programId);
if (newAccountPubkey.toBase58() !== address) throw new Error("derived address mismatch");
const space = Number(spaceArg);
const lamports = Number(rentArg);
if (!Number.isSafeInteger(space) || space < 0 ||
    !Number.isSafeInteger(lamports) || lamports <= 0) {
  throw new Error("space and rent lamports must be safe nonnegative/positive integers");
}
// The base is also the funding payer in this example. It must sign.
const instruction = SystemProgram.createAccountWithSeed({
  fromPubkey: basePubkey,
  basePubkey,
  seed,
  newAccountPubkey,
  lamports, // obtain the actual rent-exempt minimum for space from your RPC
  space,    // depends on the chosen owner and intended initialization
  programId,
});
const transaction = new Transaction().add(instruction);
console.log(JSON.stringify({
  base, owner, seed, address, space, lamports,
  instructionProgram: instruction.programId.toBase58(),
  instructions: transaction.instructions.length,
  sent: false,
}, null, 2));
// Add correct owner-program initialization instructions, a fresh blockhash,
// fee payer, and wallet signatures before sending with your chosen wallet SDK.
