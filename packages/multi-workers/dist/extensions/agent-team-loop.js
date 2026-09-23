var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __require = /* @__PURE__ */ ((x) => typeof require !== "undefined" ? require : typeof Proxy !== "undefined" ? new Proxy(x, {
  get: (a, b) => (typeof require !== "undefined" ? require : a)[b]
}) : x)(function(x) {
  if (typeof require !== "undefined") return require.apply(this, arguments);
  throw Error('Dynamic require of "' + x + '" is not supported');
});
var __commonJS = (cb, mod) => function __require2() {
  try {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  } catch (e) {
    throw mod = 0, e;
  }
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// node_modules/isexe/windows.js
var require_windows = __commonJS({
  "node_modules/isexe/windows.js"(exports, module) {
    module.exports = isexe;
    isexe.sync = sync;
    var fs30 = __require("fs");
    function checkPathExt(path34, options) {
      var pathext = options.pathExt !== void 0 ? options.pathExt : process.env.PATHEXT;
      if (!pathext) {
        return true;
      }
      pathext = pathext.split(";");
      if (pathext.indexOf("") !== -1) {
        return true;
      }
      for (var i = 0; i < pathext.length; i++) {
        var p = pathext[i].toLowerCase();
        if (p && path34.substr(-p.length).toLowerCase() === p) {
          return true;
        }
      }
      return false;
    }
    function checkStat(stat, path34, options) {
      if (!stat.isSymbolicLink() && !stat.isFile()) {
        return false;
      }
      return checkPathExt(path34, options);
    }
    function isexe(path34, options, cb) {
      fs30.stat(path34, function(er, stat) {
        cb(er, er ? false : checkStat(stat, path34, options));
      });
    }
    function sync(path34, options) {
      return checkStat(fs30.statSync(path34), path34, options);
    }
  }
});

// node_modules/isexe/mode.js
var require_mode = __commonJS({
  "node_modules/isexe/mode.js"(exports, module) {
    module.exports = isexe;
    isexe.sync = sync;
    var fs30 = __require("fs");
    function isexe(path34, options, cb) {
      fs30.stat(path34, function(er, stat) {
        cb(er, er ? false : checkStat(stat, options));
      });
    }
    function sync(path34, options) {
      return checkStat(fs30.statSync(path34), options);
    }
    function checkStat(stat, options) {
      return stat.isFile() && checkMode(stat, options);
    }
    function checkMode(stat, options) {
      var mod = stat.mode;
      var uid = stat.uid;
      var gid = stat.gid;
      var myUid = options.uid !== void 0 ? options.uid : process.getuid && process.getuid();
      var myGid = options.gid !== void 0 ? options.gid : process.getgid && process.getgid();
      var u = parseInt("100", 8);
      var g = parseInt("010", 8);
      var o = parseInt("001", 8);
      var ug = u | g;
      var ret = mod & o || mod & g && gid === myGid || mod & u && uid === myUid || mod & ug && myUid === 0;
      return ret;
    }
  }
});

// node_modules/isexe/index.js
var require_isexe = __commonJS({
  "node_modules/isexe/index.js"(exports, module) {
    var fs30 = __require("fs");
    var core;
    if (process.platform === "win32" || global.TESTING_WINDOWS) {
      core = require_windows();
    } else {
      core = require_mode();
    }
    module.exports = isexe;
    isexe.sync = sync;
    function isexe(path34, options, cb) {
      if (typeof options === "function") {
        cb = options;
        options = {};
      }
      if (!cb) {
        if (typeof Promise !== "function") {
          throw new TypeError("callback not provided");
        }
        return new Promise(function(resolve15, reject) {
          isexe(path34, options || {}, function(er, is) {
            if (er) {
              reject(er);
            } else {
              resolve15(is);
            }
          });
        });
      }
      core(path34, options || {}, function(er, is) {
        if (er) {
          if (er.code === "EACCES" || options && options.ignoreErrors) {
            er = null;
            is = false;
          }
        }
        cb(er, is);
      });
    }
    function sync(path34, options) {
      try {
        return core.sync(path34, options || {});
      } catch (er) {
        if (options && options.ignoreErrors || er.code === "EACCES") {
          return false;
        } else {
          throw er;
        }
      }
    }
  }
});

// node_modules/which/which.js
var require_which = __commonJS({
  "node_modules/which/which.js"(exports, module) {
    var isWindows = process.platform === "win32" || process.env.OSTYPE === "cygwin" || process.env.OSTYPE === "msys";
    var path34 = __require("path");
    var COLON = isWindows ? ";" : ":";
    var isexe = require_isexe();
    var getNotFoundError = (cmd) => Object.assign(new Error(`not found: ${cmd}`), { code: "ENOENT" });
    var getPathInfo = (cmd, opt) => {
      const colon = opt.colon || COLON;
      const pathEnv = cmd.match(/\//) || isWindows && cmd.match(/\\/) ? [""] : [
        // windows always checks the cwd first
        ...isWindows ? [process.cwd()] : [],
        ...(opt.path || process.env.PATH || /* istanbul ignore next: very unusual */
        "").split(colon)
      ];
      const pathExtExe = isWindows ? opt.pathExt || process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM" : "";
      const pathExt = isWindows ? pathExtExe.split(colon) : [""];
      if (isWindows) {
        if (cmd.indexOf(".") !== -1 && pathExt[0] !== "")
          pathExt.unshift("");
      }
      return {
        pathEnv,
        pathExt,
        pathExtExe
      };
    };
    var which = (cmd, opt, cb) => {
      if (typeof opt === "function") {
        cb = opt;
        opt = {};
      }
      if (!opt)
        opt = {};
      const { pathEnv, pathExt, pathExtExe } = getPathInfo(cmd, opt);
      const found = [];
      const step = (i) => new Promise((resolve15, reject) => {
        if (i === pathEnv.length)
          return opt.all && found.length ? resolve15(found) : reject(getNotFoundError(cmd));
        const ppRaw = pathEnv[i];
        const pathPart = /^".*"$/.test(ppRaw) ? ppRaw.slice(1, -1) : ppRaw;
        const pCmd = path34.join(pathPart, cmd);
        const p = !pathPart && /^\.[\\\/]/.test(cmd) ? cmd.slice(0, 2) + pCmd : pCmd;
        resolve15(subStep(p, i, 0));
      });
      const subStep = (p, i, ii) => new Promise((resolve15, reject) => {
        if (ii === pathExt.length)
          return resolve15(step(i + 1));
        const ext2 = pathExt[ii];
        isexe(p + ext2, { pathExt: pathExtExe }, (er, is) => {
          if (!er && is) {
            if (opt.all)
              found.push(p + ext2);
            else
              return resolve15(p + ext2);
          }
          return resolve15(subStep(p, i, ii + 1));
        });
      });
      return cb ? step(0).then((res) => cb(null, res), cb) : step(0);
    };
    var whichSync = (cmd, opt) => {
      opt = opt || {};
      const { pathEnv, pathExt, pathExtExe } = getPathInfo(cmd, opt);
      const found = [];
      for (let i = 0; i < pathEnv.length; i++) {
        const ppRaw = pathEnv[i];
        const pathPart = /^".*"$/.test(ppRaw) ? ppRaw.slice(1, -1) : ppRaw;
        const pCmd = path34.join(pathPart, cmd);
        const p = !pathPart && /^\.[\\\/]/.test(cmd) ? cmd.slice(0, 2) + pCmd : pCmd;
        for (let j = 0; j < pathExt.length; j++) {
          const cur = p + pathExt[j];
          try {
            const is = isexe.sync(cur, { pathExt: pathExtExe });
            if (is) {
              if (opt.all)
                found.push(cur);
              else
                return cur;
            }
          } catch (ex) {
          }
        }
      }
      if (opt.all && found.length)
        return found;
      if (opt.nothrow)
        return null;
      throw getNotFoundError(cmd);
    };
    module.exports = which;
    which.sync = whichSync;
  }
});

// node_modules/path-key/index.js
var require_path_key = __commonJS({
  "node_modules/path-key/index.js"(exports, module) {
    "use strict";
    var pathKey = (options = {}) => {
      const environment = options.env || process.env;
      const platform = options.platform || process.platform;
      if (platform !== "win32") {
        return "PATH";
      }
      return Object.keys(environment).reverse().find((key) => key.toUpperCase() === "PATH") || "Path";
    };
    module.exports = pathKey;
    module.exports.default = pathKey;
  }
});

// node_modules/cross-spawn/lib/util/resolveCommand.js
var require_resolveCommand = __commonJS({
  "node_modules/cross-spawn/lib/util/resolveCommand.js"(exports, module) {
    "use strict";
    var path34 = __require("path");
    var which = require_which();
    var getPathKey = require_path_key();
    function resolveCommandAttempt(parsed, withoutPathExt) {
      const env = parsed.options.env || process.env;
      const cwd = process.cwd();
      const hasCustomCwd = parsed.options.cwd != null;
      const shouldSwitchCwd = hasCustomCwd && process.chdir !== void 0 && !process.chdir.disabled;
      if (shouldSwitchCwd) {
        try {
          process.chdir(parsed.options.cwd);
        } catch (err) {
        }
      }
      let resolved;
      try {
        resolved = which.sync(parsed.command, {
          path: env[getPathKey({ env })],
          pathExt: withoutPathExt ? path34.delimiter : void 0
        });
      } catch (e) {
      } finally {
        if (shouldSwitchCwd) {
          process.chdir(cwd);
        }
      }
      if (resolved) {
        resolved = path34.resolve(hasCustomCwd ? parsed.options.cwd : "", resolved);
      }
      return resolved;
    }
    function resolveCommand(parsed) {
      return resolveCommandAttempt(parsed) || resolveCommandAttempt(parsed, true);
    }
    module.exports = resolveCommand;
  }
});

// node_modules/cross-spawn/lib/util/escape.js
var require_escape = __commonJS({
  "node_modules/cross-spawn/lib/util/escape.js"(exports, module) {
    "use strict";
    var metaCharsRegExp = /([()\][%!^"`<>&|;, *?])/g;
    function escapeCommand(arg) {
      arg = arg.replace(metaCharsRegExp, "^$1");
      return arg;
    }
    function escapeArgument(arg, doubleEscapeMetaChars) {
      arg = `${arg}`;
      arg = arg.replace(/(?=(\\+?)?)\1"/g, '$1$1\\"');
      arg = arg.replace(/(?=(\\+?)?)\1$/, "$1$1");
      arg = `"${arg}"`;
      arg = arg.replace(metaCharsRegExp, "^$1");
      if (doubleEscapeMetaChars) {
        arg = arg.replace(metaCharsRegExp, "^$1");
      }
      return arg;
    }
    module.exports.command = escapeCommand;
    module.exports.argument = escapeArgument;
  }
});

// node_modules/shebang-regex/index.js
var require_shebang_regex = __commonJS({
  "node_modules/shebang-regex/index.js"(exports, module) {
    "use strict";
    module.exports = /^#!(.*)/;
  }
});

// node_modules/shebang-command/index.js
var require_shebang_command = __commonJS({
  "node_modules/shebang-command/index.js"(exports, module) {
    "use strict";
    var shebangRegex = require_shebang_regex();
    module.exports = (string = "") => {
      const match2 = string.match(shebangRegex);
      if (!match2) {
        return null;
      }
      const [path34, argument] = match2[0].replace(/#! ?/, "").split(" ");
      const binary = path34.split("/").pop();
      if (binary === "env") {
        return argument;
      }
      return argument ? `${binary} ${argument}` : binary;
    };
  }
});

// node_modules/cross-spawn/lib/util/readShebang.js
var require_readShebang = __commonJS({
  "node_modules/cross-spawn/lib/util/readShebang.js"(exports, module) {
    "use strict";
    var fs30 = __require("fs");
    var shebangCommand = require_shebang_command();
    function readShebang(command) {
      const size = 150;
      const buffer = Buffer.alloc(size);
      let fd;
      try {
        fd = fs30.openSync(command, "r");
        fs30.readSync(fd, buffer, 0, size, 0);
        fs30.closeSync(fd);
      } catch (e) {
      }
      return shebangCommand(buffer.toString());
    }
    module.exports = readShebang;
  }
});

// node_modules/cross-spawn/lib/parse.js
var require_parse = __commonJS({
  "node_modules/cross-spawn/lib/parse.js"(exports, module) {
    "use strict";
    var path34 = __require("path");
    var resolveCommand = require_resolveCommand();
    var escape2 = require_escape();
    var readShebang = require_readShebang();
    var isWin = process.platform === "win32";
    var isExecutableRegExp = /\.(?:com|exe)$/i;
    var isCmdShimRegExp = /node_modules[\\/].bin[\\/][^\\/]+\.cmd$/i;
    function detectShebang(parsed) {
      parsed.file = resolveCommand(parsed);
      const shebang = parsed.file && readShebang(parsed.file);
      if (shebang) {
        parsed.args.unshift(parsed.file);
        parsed.command = shebang;
        return resolveCommand(parsed);
      }
      return parsed.file;
    }
    function parseNonShell(parsed) {
      if (!isWin) {
        return parsed;
      }
      const commandFile = detectShebang(parsed);
      const needsShell = !isExecutableRegExp.test(commandFile);
      if (parsed.options.forceShell || needsShell) {
        const needsDoubleEscapeMetaChars = isCmdShimRegExp.test(commandFile);
        parsed.command = path34.normalize(parsed.command);
        parsed.command = escape2.command(parsed.command);
        parsed.args = parsed.args.map((arg) => escape2.argument(arg, needsDoubleEscapeMetaChars));
        const shellCommand = [parsed.command].concat(parsed.args).join(" ");
        parsed.args = ["/d", "/s", "/c", `"${shellCommand}"`];
        parsed.command = process.env.comspec || "cmd.exe";
        parsed.options.windowsVerbatimArguments = true;
      }
      return parsed;
    }
    function parse3(command, args, options) {
      if (args && !Array.isArray(args)) {
        options = args;
        args = null;
      }
      args = args ? args.slice(0) : [];
      options = Object.assign({}, options);
      const parsed = {
        command,
        args,
        options,
        file: void 0,
        original: {
          command,
          args
        }
      };
      return options.shell ? parsed : parseNonShell(parsed);
    }
    module.exports = parse3;
  }
});

// node_modules/cross-spawn/lib/enoent.js
var require_enoent = __commonJS({
  "node_modules/cross-spawn/lib/enoent.js"(exports, module) {
    "use strict";
    var isWin = process.platform === "win32";
    function notFoundError(original, syscall) {
      return Object.assign(new Error(`${syscall} ${original.command} ENOENT`), {
        code: "ENOENT",
        errno: "ENOENT",
        syscall: `${syscall} ${original.command}`,
        path: original.command,
        spawnargs: original.args
      });
    }
    function hookChildProcess(cp, parsed) {
      if (!isWin) {
        return;
      }
      const originalEmit = cp.emit;
      cp.emit = function(name, arg1) {
        if (name === "exit") {
          const err = verifyENOENT(arg1, parsed);
          if (err) {
            return originalEmit.call(cp, "error", err);
          }
        }
        return originalEmit.apply(cp, arguments);
      };
    }
    function verifyENOENT(status, parsed) {
      if (isWin && status === 1 && !parsed.file) {
        return notFoundError(parsed.original, "spawn");
      }
      return null;
    }
    function verifyENOENTSync(status, parsed) {
      if (isWin && status === 1 && !parsed.file) {
        return notFoundError(parsed.original, "spawnSync");
      }
      return null;
    }
    module.exports = {
      hookChildProcess,
      verifyENOENT,
      verifyENOENTSync,
      notFoundError
    };
  }
});

// node_modules/cross-spawn/index.js
var require_cross_spawn = __commonJS({
  "node_modules/cross-spawn/index.js"(exports, module) {
    "use strict";
    var cp = __require("child_process");
    var parse3 = require_parse();
    var enoent = require_enoent();
    function spawn4(command, args, options) {
      const parsed = parse3(command, args, options);
      const spawned = cp.spawn(parsed.command, parsed.args, parsed.options);
      enoent.hookChildProcess(spawned, parsed);
      return spawned;
    }
    function spawnSync4(command, args, options) {
      const parsed = parse3(command, args, options);
      const result = cp.spawnSync(parsed.command, parsed.args, parsed.options);
      result.error = result.error || enoent.verifyENOENTSync(result.status, parsed);
      return result;
    }
    module.exports = spawn4;
    module.exports.spawn = spawn4;
    module.exports.sync = spawnSync4;
    module.exports._parse = parse3;
    module.exports._enoent = enoent;
  }
});

// node_modules/yaml/dist/nodes/identity.js
var require_identity = __commonJS({
  "node_modules/yaml/dist/nodes/identity.js"(exports) {
    "use strict";
    var ALIAS = /* @__PURE__ */ Symbol.for("yaml.alias");
    var DOC = /* @__PURE__ */ Symbol.for("yaml.document");
    var MAP = /* @__PURE__ */ Symbol.for("yaml.map");
    var PAIR = /* @__PURE__ */ Symbol.for("yaml.pair");
    var SCALAR = /* @__PURE__ */ Symbol.for("yaml.scalar");
    var SEQ = /* @__PURE__ */ Symbol.for("yaml.seq");
    var NODE_TYPE = /* @__PURE__ */ Symbol.for("yaml.node.type");
    var isAlias = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === ALIAS;
    var isDocument = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === DOC;
    var isMap2 = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === MAP;
    var isPair = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === PAIR;
    var isScalar2 = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === SCALAR;
    var isSeq = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === SEQ;
    function isCollection(node) {
      if (node && typeof node === "object")
        switch (node[NODE_TYPE]) {
          case MAP:
          case SEQ:
            return true;
        }
      return false;
    }
    function isNode(node) {
      if (node && typeof node === "object")
        switch (node[NODE_TYPE]) {
          case ALIAS:
          case MAP:
          case SCALAR:
          case SEQ:
            return true;
        }
      return false;
    }
    var hasAnchor = (node) => (isScalar2(node) || isCollection(node)) && !!node.anchor;
    exports.ALIAS = ALIAS;
    exports.DOC = DOC;
    exports.MAP = MAP;
    exports.NODE_TYPE = NODE_TYPE;
    exports.PAIR = PAIR;
    exports.SCALAR = SCALAR;
    exports.SEQ = SEQ;
    exports.hasAnchor = hasAnchor;
    exports.isAlias = isAlias;
    exports.isCollection = isCollection;
    exports.isDocument = isDocument;
    exports.isMap = isMap2;
    exports.isNode = isNode;
    exports.isPair = isPair;
    exports.isScalar = isScalar2;
    exports.isSeq = isSeq;
  }
});

// node_modules/yaml/dist/visit.js
var require_visit = __commonJS({
  "node_modules/yaml/dist/visit.js"(exports) {
    "use strict";
    var identity = require_identity();
    var BREAK = /* @__PURE__ */ Symbol("break visit");
    var SKIP = /* @__PURE__ */ Symbol("skip children");
    var REMOVE = /* @__PURE__ */ Symbol("remove node");
    function visit(node, visitor) {
      const visitor_ = initVisitor(visitor);
      if (identity.isDocument(node)) {
        const cd = visit_(null, node.contents, visitor_, Object.freeze([node]));
        if (cd === REMOVE)
          node.contents = null;
      } else
        visit_(null, node, visitor_, Object.freeze([]));
    }
    visit.BREAK = BREAK;
    visit.SKIP = SKIP;
    visit.REMOVE = REMOVE;
    function visit_(key, node, visitor, path34) {
      const ctrl = callVisitor(key, node, visitor, path34);
      if (identity.isNode(ctrl) || identity.isPair(ctrl)) {
        replaceNode(key, path34, ctrl);
        return visit_(key, ctrl, visitor, path34);
      }
      if (typeof ctrl !== "symbol") {
        if (identity.isCollection(node)) {
          path34 = Object.freeze(path34.concat(node));
          for (let i = 0; i < node.items.length; ++i) {
            const ci = visit_(i, node.items[i], visitor, path34);
            if (typeof ci === "number")
              i = ci - 1;
            else if (ci === BREAK)
              return BREAK;
            else if (ci === REMOVE) {
              node.items.splice(i, 1);
              i -= 1;
            }
          }
        } else if (identity.isPair(node)) {
          path34 = Object.freeze(path34.concat(node));
          const ck = visit_("key", node.key, visitor, path34);
          if (ck === BREAK)
            return BREAK;
          else if (ck === REMOVE)
            node.key = null;
          const cv = visit_("value", node.value, visitor, path34);
          if (cv === BREAK)
            return BREAK;
          else if (cv === REMOVE)
            node.value = null;
        }
      }
      return ctrl;
    }
    async function visitAsync(node, visitor) {
      const visitor_ = initVisitor(visitor);
      if (identity.isDocument(node)) {
        const cd = await visitAsync_(null, node.contents, visitor_, Object.freeze([node]));
        if (cd === REMOVE)
          node.contents = null;
      } else
        await visitAsync_(null, node, visitor_, Object.freeze([]));
    }
    visitAsync.BREAK = BREAK;
    visitAsync.SKIP = SKIP;
    visitAsync.REMOVE = REMOVE;
    async function visitAsync_(key, node, visitor, path34) {
      const ctrl = await callVisitor(key, node, visitor, path34);
      if (identity.isNode(ctrl) || identity.isPair(ctrl)) {
        replaceNode(key, path34, ctrl);
        return visitAsync_(key, ctrl, visitor, path34);
      }
      if (typeof ctrl !== "symbol") {
        if (identity.isCollection(node)) {
          path34 = Object.freeze(path34.concat(node));
          for (let i = 0; i < node.items.length; ++i) {
            const ci = await visitAsync_(i, node.items[i], visitor, path34);
            if (typeof ci === "number")
              i = ci - 1;
            else if (ci === BREAK)
              return BREAK;
            else if (ci === REMOVE) {
              node.items.splice(i, 1);
              i -= 1;
            }
          }
        } else if (identity.isPair(node)) {
          path34 = Object.freeze(path34.concat(node));
          const ck = await visitAsync_("key", node.key, visitor, path34);
          if (ck === BREAK)
            return BREAK;
          else if (ck === REMOVE)
            node.key = null;
          const cv = await visitAsync_("value", node.value, visitor, path34);
          if (cv === BREAK)
            return BREAK;
          else if (cv === REMOVE)
            node.value = null;
        }
      }
      return ctrl;
    }
    function initVisitor(visitor) {
      if (typeof visitor === "object" && (visitor.Collection || visitor.Node || visitor.Value)) {
        return Object.assign({
          Alias: visitor.Node,
          Map: visitor.Node,
          Scalar: visitor.Node,
          Seq: visitor.Node
        }, visitor.Value && {
          Map: visitor.Value,
          Scalar: visitor.Value,
          Seq: visitor.Value
        }, visitor.Collection && {
          Map: visitor.Collection,
          Seq: visitor.Collection
        }, visitor);
      }
      return visitor;
    }
    function callVisitor(key, node, visitor, path34) {
      if (typeof visitor === "function")
        return visitor(key, node, path34);
      if (identity.isMap(node))
        return visitor.Map?.(key, node, path34);
      if (identity.isSeq(node))
        return visitor.Seq?.(key, node, path34);
      if (identity.isPair(node))
        return visitor.Pair?.(key, node, path34);
      if (identity.isScalar(node))
        return visitor.Scalar?.(key, node, path34);
      if (identity.isAlias(node))
        return visitor.Alias?.(key, node, path34);
      return void 0;
    }
    function replaceNode(key, path34, node) {
      const parent = path34[path34.length - 1];
      if (identity.isCollection(parent)) {
        parent.items[key] = node;
      } else if (identity.isPair(parent)) {
        if (key === "key")
          parent.key = node;
        else
          parent.value = node;
      } else if (identity.isDocument(parent)) {
        parent.contents = node;
      } else {
        const pt = identity.isAlias(parent) ? "alias" : "scalar";
        throw new Error(`Cannot replace node with ${pt} parent`);
      }
    }
    exports.visit = visit;
    exports.visitAsync = visitAsync;
  }
});

// node_modules/yaml/dist/doc/directives.js
var require_directives = __commonJS({
  "node_modules/yaml/dist/doc/directives.js"(exports) {
    "use strict";
    var identity = require_identity();
    var visit = require_visit();
    var escapeChars = {
      "!": "%21",
      ",": "%2C",
      "[": "%5B",
      "]": "%5D",
      "{": "%7B",
      "}": "%7D"
    };
    var escapeTagName = (tn) => tn.replace(/[!,[\]{}]/g, (ch) => escapeChars[ch]);
    var Directives = class _Directives {
      constructor(yaml, tags) {
        this.docStart = null;
        this.docEnd = false;
        this.yaml = Object.assign({}, _Directives.defaultYaml, yaml);
        this.tags = Object.assign({}, _Directives.defaultTags, tags);
      }
      clone() {
        const copy = new _Directives(this.yaml, this.tags);
        copy.docStart = this.docStart;
        return copy;
      }
      /**
       * During parsing, get a Directives instance for the current document and
       * update the stream state according to the current version's spec.
       */
      atDocument() {
        const res = new _Directives(this.yaml, this.tags);
        switch (this.yaml.version) {
          case "1.1":
            this.atNextDocument = true;
            break;
          case "1.2":
            this.atNextDocument = false;
            this.yaml = {
              explicit: _Directives.defaultYaml.explicit,
              version: "1.2"
            };
            this.tags = Object.assign({}, _Directives.defaultTags);
            break;
        }
        return res;
      }
      /**
       * @param onError - May be called even if the action was successful
       * @returns `true` on success
       */
      add(line, onError) {
        if (this.atNextDocument) {
          this.yaml = { explicit: _Directives.defaultYaml.explicit, version: "1.1" };
          this.tags = Object.assign({}, _Directives.defaultTags);
          this.atNextDocument = false;
        }
        const parts = line.trim().split(/[ \t]+/);
        const name = parts.shift();
        switch (name) {
          case "%TAG": {
            if (parts.length !== 2) {
              onError(0, "%TAG directive should contain exactly two parts");
              if (parts.length < 2)
                return false;
            }
            const [handle, prefix] = parts;
            this.tags[handle] = prefix;
            return true;
          }
          case "%YAML": {
            this.yaml.explicit = true;
            if (parts.length !== 1) {
              onError(0, "%YAML directive should contain exactly one part");
              return false;
            }
            const [version] = parts;
            if (version === "1.1" || version === "1.2") {
              this.yaml.version = version;
              return true;
            } else {
              const isValid = /^\d+\.\d+$/.test(version);
              onError(6, `Unsupported YAML version ${version}`, isValid);
              return false;
            }
          }
          default:
            onError(0, `Unknown directive ${name}`, true);
            return false;
        }
      }
      /**
       * Resolves a tag, matching handles to those defined in %TAG directives.
       *
       * @returns Resolved tag, which may also be the non-specific tag `'!'` or a
       *   `'!local'` tag, or `null` if unresolvable.
       */
      tagName(source, onError) {
        if (source === "!")
          return "!";
        if (source[0] !== "!") {
          onError(`Not a valid tag: ${source}`);
          return null;
        }
        if (source[1] === "<") {
          const verbatim = source.slice(2, -1);
          if (verbatim === "!" || verbatim === "!!") {
            onError(`Verbatim tags aren't resolved, so ${source} is invalid.`);
            return null;
          }
          if (source[source.length - 1] !== ">")
            onError("Verbatim tags must end with a >");
          return verbatim;
        }
        const [, handle, suffix] = source.match(/^(.*!)([^!]*)$/s);
        if (!suffix)
          onError(`The ${source} tag has no suffix`);
        const prefix = this.tags[handle];
        if (prefix) {
          try {
            return prefix + decodeURIComponent(suffix);
          } catch (error) {
            onError(String(error));
            return null;
          }
        }
        if (handle === "!")
          return source;
        onError(`Could not resolve tag: ${source}`);
        return null;
      }
      /**
       * Given a fully resolved tag, returns its printable string form,
       * taking into account current tag prefixes and defaults.
       */
      tagString(tag) {
        for (const [handle, prefix] of Object.entries(this.tags)) {
          if (tag.startsWith(prefix))
            return handle + escapeTagName(tag.substring(prefix.length));
        }
        return tag[0] === "!" ? tag : `!<${tag}>`;
      }
      toString(doc) {
        const lines = this.yaml.explicit ? [`%YAML ${this.yaml.version || "1.2"}`] : [];
        const tagEntries = Object.entries(this.tags);
        let tagNames;
        if (doc && tagEntries.length > 0 && identity.isNode(doc.contents)) {
          const tags = {};
          visit.visit(doc.contents, (_key, node) => {
            if (identity.isNode(node) && node.tag)
              tags[node.tag] = true;
          });
          tagNames = Object.keys(tags);
        } else
          tagNames = [];
        for (const [handle, prefix] of tagEntries) {
          if (handle === "!!" && prefix === "tag:yaml.org,2002:")
            continue;
          if (!doc || tagNames.some((tn) => tn.startsWith(prefix)))
            lines.push(`%TAG ${handle} ${prefix}`);
        }
        return lines.join("\n");
      }
    };
    Directives.defaultYaml = { explicit: false, version: "1.2" };
    Directives.defaultTags = { "!!": "tag:yaml.org,2002:" };
    exports.Directives = Directives;
  }
});

// node_modules/yaml/dist/doc/anchors.js
var require_anchors = __commonJS({
  "node_modules/yaml/dist/doc/anchors.js"(exports) {
    "use strict";
    var identity = require_identity();
    var visit = require_visit();
    function anchorIsValid(anchor) {
      if (/[\x00-\x19\s,[\]{}]/.test(anchor)) {
        const sa = JSON.stringify(anchor);
        const msg = `Anchor must not contain whitespace or control characters: ${sa}`;
        throw new Error(msg);
      }
      return true;
    }
    function anchorNames(root) {
      const anchors = /* @__PURE__ */ new Set();
      visit.visit(root, {
        Value(_key, node) {
          if (node.anchor)
            anchors.add(node.anchor);
        }
      });
      return anchors;
    }
    function findNewAnchor(prefix, exclude) {
      for (let i = 1; true; ++i) {
        const name = `${prefix}${i}`;
        if (!exclude.has(name))
          return name;
      }
    }
    function createNodeAnchors(doc, prefix) {
      const aliasObjects = [];
      const sourceObjects = /* @__PURE__ */ new Map();
      let prevAnchors = null;
      return {
        onAnchor: (source) => {
          aliasObjects.push(source);
          prevAnchors ?? (prevAnchors = anchorNames(doc));
          const anchor = findNewAnchor(prefix, prevAnchors);
          prevAnchors.add(anchor);
          return anchor;
        },
        /**
         * With circular references, the source node is only resolved after all
         * of its child nodes are. This is why anchors are set only after all of
         * the nodes have been created.
         */
        setAnchors: () => {
          for (const source of aliasObjects) {
            const ref = sourceObjects.get(source);
            if (typeof ref === "object" && ref.anchor && (identity.isScalar(ref.node) || identity.isCollection(ref.node))) {
              ref.node.anchor = ref.anchor;
            } else {
              const error = new Error("Failed to resolve repeated object (this should not happen)");
              error.source = source;
              throw error;
            }
          }
        },
        sourceObjects
      };
    }
    exports.anchorIsValid = anchorIsValid;
    exports.anchorNames = anchorNames;
    exports.createNodeAnchors = createNodeAnchors;
    exports.findNewAnchor = findNewAnchor;
  }
});

// node_modules/yaml/dist/doc/applyReviver.js
var require_applyReviver = __commonJS({
  "node_modules/yaml/dist/doc/applyReviver.js"(exports) {
    "use strict";
    function applyReviver(reviver, obj, key, val) {
      if (val && typeof val === "object") {
        if (Array.isArray(val)) {
          for (let i = 0, len = val.length; i < len; ++i) {
            const v0 = val[i];
            const v1 = applyReviver(reviver, val, String(i), v0);
            if (v1 === void 0)
              delete val[i];
            else if (v1 !== v0)
              val[i] = v1;
          }
        } else if (val instanceof Map) {
          for (const k of Array.from(val.keys())) {
            const v0 = val.get(k);
            const v1 = applyReviver(reviver, val, k, v0);
            if (v1 === void 0)
              val.delete(k);
            else if (v1 !== v0)
              val.set(k, v1);
          }
        } else if (val instanceof Set) {
          for (const v0 of Array.from(val)) {
            const v1 = applyReviver(reviver, val, v0, v0);
            if (v1 === void 0)
              val.delete(v0);
            else if (v1 !== v0) {
              val.delete(v0);
              val.add(v1);
            }
          }
        } else {
          for (const [k, v0] of Object.entries(val)) {
            const v1 = applyReviver(reviver, val, k, v0);
            if (v1 === void 0)
              delete val[k];
            else if (v1 !== v0)
              val[k] = v1;
          }
        }
      }
      return reviver.call(obj, key, val);
    }
    exports.applyReviver = applyReviver;
  }
});

// node_modules/yaml/dist/nodes/toJS.js
var require_toJS = __commonJS({
  "node_modules/yaml/dist/nodes/toJS.js"(exports) {
    "use strict";
    var identity = require_identity();
    function toJS(value, arg, ctx) {
      if (Array.isArray(value))
        return value.map((v, i) => toJS(v, String(i), ctx));
      if (value && typeof value.toJSON === "function") {
        if (!ctx || !identity.hasAnchor(value))
          return value.toJSON(arg, ctx);
        const data = { aliasCount: 0, count: 1, res: void 0 };
        ctx.anchors.set(value, data);
        ctx.onCreate = (res2) => {
          data.res = res2;
          delete ctx.onCreate;
        };
        const res = value.toJSON(arg, ctx);
        if (ctx.onCreate)
          ctx.onCreate(res);
        return res;
      }
      if (typeof value === "bigint" && !ctx?.keep)
        return Number(value);
      return value;
    }
    exports.toJS = toJS;
  }
});

// node_modules/yaml/dist/nodes/Node.js
var require_Node = __commonJS({
  "node_modules/yaml/dist/nodes/Node.js"(exports) {
    "use strict";
    var applyReviver = require_applyReviver();
    var identity = require_identity();
    var toJS = require_toJS();
    var NodeBase = class {
      constructor(type) {
        Object.defineProperty(this, identity.NODE_TYPE, { value: type });
      }
      /** Create a copy of this node.  */
      clone() {
        const copy = Object.create(Object.getPrototypeOf(this), Object.getOwnPropertyDescriptors(this));
        if (this.range)
          copy.range = this.range.slice();
        return copy;
      }
      /** A plain JavaScript representation of this node. */
      toJS(doc, { mapAsMap, maxAliasCount, onAnchor, reviver } = {}) {
        if (!identity.isDocument(doc))
          throw new TypeError("A document argument is required");
        const ctx = {
          anchors: /* @__PURE__ */ new Map(),
          doc,
          keep: true,
          mapAsMap: mapAsMap === true,
          mapKeyWarned: false,
          maxAliasCount: typeof maxAliasCount === "number" ? maxAliasCount : 100
        };
        const res = toJS.toJS(this, "", ctx);
        if (typeof onAnchor === "function")
          for (const { count: count2, res: res2 } of ctx.anchors.values())
            onAnchor(res2, count2);
        return typeof reviver === "function" ? applyReviver.applyReviver(reviver, { "": res }, "", res) : res;
      }
    };
    exports.NodeBase = NodeBase;
  }
});

// node_modules/yaml/dist/nodes/Alias.js
var require_Alias = __commonJS({
  "node_modules/yaml/dist/nodes/Alias.js"(exports) {
    "use strict";
    var anchors = require_anchors();
    var visit = require_visit();
    var identity = require_identity();
    var Node = require_Node();
    var toJS = require_toJS();
    var Alias = class extends Node.NodeBase {
      constructor(source) {
        super(identity.ALIAS);
        this.source = source;
        Object.defineProperty(this, "tag", {
          set() {
            throw new Error("Alias nodes cannot have tags");
          }
        });
      }
      /**
       * Resolve the value of this alias within `doc`, finding the last
       * instance of the `source` anchor before this node.
       */
      resolve(doc, ctx) {
        if (ctx?.maxAliasCount === 0)
          throw new ReferenceError("Alias resolution is disabled");
        let nodes;
        if (ctx?.aliasResolveCache) {
          nodes = ctx.aliasResolveCache;
        } else {
          nodes = [];
          visit.visit(doc, {
            Node: (_key, node) => {
              if (identity.isAlias(node) || identity.hasAnchor(node))
                nodes.push(node);
            }
          });
          if (ctx)
            ctx.aliasResolveCache = nodes;
        }
        let found = void 0;
        for (const node of nodes) {
          if (node === this)
            break;
          if (node.anchor === this.source)
            found = node;
        }
        return found;
      }
      toJSON(_arg, ctx) {
        if (!ctx)
          return { source: this.source };
        const { anchors: anchors2, doc, maxAliasCount } = ctx;
        const source = this.resolve(doc, ctx);
        if (!source) {
          const msg = `Unresolved alias (the anchor must be set before the alias): ${this.source}`;
          throw new ReferenceError(msg);
        }
        let data = anchors2.get(source);
        if (!data) {
          toJS.toJS(source, null, ctx);
          data = anchors2.get(source);
        }
        if (data?.res === void 0) {
          const msg = "This should not happen: Alias anchor was not resolved?";
          throw new ReferenceError(msg);
        }
        if (maxAliasCount >= 0) {
          data.count += 1;
          if (data.aliasCount === 0)
            data.aliasCount = getAliasCount(doc, source, anchors2);
          if (data.count * data.aliasCount > maxAliasCount) {
            const msg = "Excessive alias count indicates a resource exhaustion attack";
            throw new ReferenceError(msg);
          }
        }
        return data.res;
      }
      toString(ctx, _onComment, _onChompKeep) {
        const src = `*${this.source}`;
        if (ctx) {
          anchors.anchorIsValid(this.source);
          if (ctx.options.verifyAliasOrder && !ctx.anchors.has(this.source)) {
            const msg = `Unresolved alias (the anchor must be set before the alias): ${this.source}`;
            throw new Error(msg);
          }
          if (ctx.implicitKey)
            return `${src} `;
        }
        return src;
      }
    };
    function getAliasCount(doc, node, anchors2) {
      if (identity.isAlias(node)) {
        const source = node.resolve(doc);
        const anchor = anchors2 && source && anchors2.get(source);
        return anchor ? anchor.count * anchor.aliasCount : 0;
      } else if (identity.isCollection(node)) {
        let count2 = 0;
        for (const item of node.items) {
          const c = getAliasCount(doc, item, anchors2);
          if (c > count2)
            count2 = c;
        }
        return count2;
      } else if (identity.isPair(node)) {
        const kc = getAliasCount(doc, node.key, anchors2);
        const vc = getAliasCount(doc, node.value, anchors2);
        return Math.max(kc, vc);
      }
      return 1;
    }
    exports.Alias = Alias;
  }
});

// node_modules/yaml/dist/nodes/Scalar.js
var require_Scalar = __commonJS({
  "node_modules/yaml/dist/nodes/Scalar.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Node = require_Node();
    var toJS = require_toJS();
    var isScalarValue = (value) => !value || typeof value !== "function" && typeof value !== "object";
    var Scalar = class extends Node.NodeBase {
      constructor(value) {
        super(identity.SCALAR);
        this.value = value;
      }
      toJSON(arg, ctx) {
        return ctx?.keep ? this.value : toJS.toJS(this.value, arg, ctx);
      }
      toString() {
        return String(this.value);
      }
    };
    Scalar.BLOCK_FOLDED = "BLOCK_FOLDED";
    Scalar.BLOCK_LITERAL = "BLOCK_LITERAL";
    Scalar.PLAIN = "PLAIN";
    Scalar.QUOTE_DOUBLE = "QUOTE_DOUBLE";
    Scalar.QUOTE_SINGLE = "QUOTE_SINGLE";
    exports.Scalar = Scalar;
    exports.isScalarValue = isScalarValue;
  }
});

// node_modules/yaml/dist/doc/createNode.js
var require_createNode = __commonJS({
  "node_modules/yaml/dist/doc/createNode.js"(exports) {
    "use strict";
    var Alias = require_Alias();
    var identity = require_identity();
    var Scalar = require_Scalar();
    var defaultTagPrefix = "tag:yaml.org,2002:";
    function findTagObject(value, tagName, tags) {
      if (tagName) {
        const match2 = tags.filter((t) => t.tag === tagName);
        const tagObj = match2.find((t) => !t.format) ?? match2[0];
        if (!tagObj)
          throw new Error(`Tag ${tagName} not found`);
        return tagObj;
      }
      return tags.find((t) => t.identify?.(value) && !t.format);
    }
    function createNode(value, tagName, ctx) {
      if (identity.isDocument(value))
        value = value.contents;
      if (identity.isNode(value))
        return value;
      if (identity.isPair(value)) {
        const map = ctx.schema[identity.MAP].createNode?.(ctx.schema, null, ctx);
        map.items.push(value);
        return map;
      }
      if (value instanceof String || value instanceof Number || value instanceof Boolean || typeof BigInt !== "undefined" && value instanceof BigInt) {
        value = value.valueOf();
      }
      const { aliasDuplicateObjects, onAnchor, onTagObj, schema, sourceObjects } = ctx;
      let ref = void 0;
      if (aliasDuplicateObjects && value && typeof value === "object") {
        ref = sourceObjects.get(value);
        if (ref) {
          ref.anchor ?? (ref.anchor = onAnchor(value));
          return new Alias.Alias(ref.anchor);
        } else {
          ref = { anchor: null, node: null };
          sourceObjects.set(value, ref);
        }
      }
      if (tagName?.startsWith("!!"))
        tagName = defaultTagPrefix + tagName.slice(2);
      let tagObj = findTagObject(value, tagName, schema.tags);
      if (!tagObj) {
        if (value && typeof value.toJSON === "function") {
          value = value.toJSON();
        }
        if (!value || typeof value !== "object") {
          const node2 = new Scalar.Scalar(value);
          if (ref)
            ref.node = node2;
          return node2;
        }
        tagObj = value instanceof Map ? schema[identity.MAP] : Symbol.iterator in Object(value) ? schema[identity.SEQ] : schema[identity.MAP];
      }
      if (onTagObj) {
        onTagObj(tagObj);
        delete ctx.onTagObj;
      }
      const node = tagObj?.createNode ? tagObj.createNode(ctx.schema, value, ctx) : typeof tagObj?.nodeClass?.from === "function" ? tagObj.nodeClass.from(ctx.schema, value, ctx) : new Scalar.Scalar(value);
      if (tagName)
        node.tag = tagName;
      else if (!tagObj.default)
        node.tag = tagObj.tag;
      if (ref)
        ref.node = node;
      return node;
    }
    exports.createNode = createNode;
  }
});

// node_modules/yaml/dist/nodes/Collection.js
var require_Collection = __commonJS({
  "node_modules/yaml/dist/nodes/Collection.js"(exports) {
    "use strict";
    var createNode = require_createNode();
    var identity = require_identity();
    var Node = require_Node();
    function collectionFromPath(schema, path34, value) {
      let v = value;
      for (let i = path34.length - 1; i >= 0; --i) {
        const k = path34[i];
        if (typeof k === "number" && Number.isInteger(k) && k >= 0) {
          const a = [];
          a[k] = v;
          v = a;
        } else {
          v = /* @__PURE__ */ new Map([[k, v]]);
        }
      }
      return createNode.createNode(v, void 0, {
        aliasDuplicateObjects: false,
        keepUndefined: false,
        onAnchor: () => {
          throw new Error("This should not happen, please report a bug.");
        },
        schema,
        sourceObjects: /* @__PURE__ */ new Map()
      });
    }
    var isEmptyPath = (path34) => path34 == null || typeof path34 === "object" && !!path34[Symbol.iterator]().next().done;
    var Collection = class extends Node.NodeBase {
      constructor(type, schema) {
        super(type);
        Object.defineProperty(this, "schema", {
          value: schema,
          configurable: true,
          enumerable: false,
          writable: true
        });
      }
      /**
       * Create a copy of this collection.
       *
       * @param schema - If defined, overwrites the original's schema
       */
      clone(schema) {
        const copy = Object.create(Object.getPrototypeOf(this), Object.getOwnPropertyDescriptors(this));
        if (schema)
          copy.schema = schema;
        copy.items = copy.items.map((it) => identity.isNode(it) || identity.isPair(it) ? it.clone(schema) : it);
        if (this.range)
          copy.range = this.range.slice();
        return copy;
      }
      /**
       * Adds a value to the collection. For `!!map` and `!!omap` the value must
       * be a Pair instance or a `{ key, value }` object, which may not have a key
       * that already exists in the map.
       */
      addIn(path34, value) {
        if (isEmptyPath(path34))
          this.add(value);
        else {
          const [key, ...rest] = path34;
          const node = this.get(key, true);
          if (identity.isCollection(node))
            node.addIn(rest, value);
          else if (node === void 0 && this.schema)
            this.set(key, collectionFromPath(this.schema, rest, value));
          else
            throw new Error(`Expected YAML collection at ${key}. Remaining path: ${rest}`);
        }
      }
      /**
       * Removes a value from the collection.
       * @returns `true` if the item was found and removed.
       */
      deleteIn(path34) {
        const [key, ...rest] = path34;
        if (rest.length === 0)
          return this.delete(key);
        const node = this.get(key, true);
        if (identity.isCollection(node))
          return node.deleteIn(rest);
        else
          throw new Error(`Expected YAML collection at ${key}. Remaining path: ${rest}`);
      }
      /**
       * Returns item at `key`, or `undefined` if not found. By default unwraps
       * scalar values from their surrounding node; to disable set `keepScalar` to
       * `true` (collections are always returned intact).
       */
      getIn(path34, keepScalar) {
        const [key, ...rest] = path34;
        const node = this.get(key, true);
        if (rest.length === 0)
          return !keepScalar && identity.isScalar(node) ? node.value : node;
        else
          return identity.isCollection(node) ? node.getIn(rest, keepScalar) : void 0;
      }
      hasAllNullValues(allowScalar) {
        return this.items.every((node) => {
          if (!identity.isPair(node))
            return false;
          const n = node.value;
          return n == null || allowScalar && identity.isScalar(n) && n.value == null && !n.commentBefore && !n.comment && !n.tag;
        });
      }
      /**
       * Checks if the collection includes a value with the key `key`.
       */
      hasIn(path34) {
        const [key, ...rest] = path34;
        if (rest.length === 0)
          return this.has(key);
        const node = this.get(key, true);
        return identity.isCollection(node) ? node.hasIn(rest) : false;
      }
      /**
       * Sets a value in this collection. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       */
      setIn(path34, value) {
        const [key, ...rest] = path34;
        if (rest.length === 0) {
          this.set(key, value);
        } else {
          const node = this.get(key, true);
          if (identity.isCollection(node))
            node.setIn(rest, value);
          else if (node === void 0 && this.schema)
            this.set(key, collectionFromPath(this.schema, rest, value));
          else
            throw new Error(`Expected YAML collection at ${key}. Remaining path: ${rest}`);
        }
      }
    };
    exports.Collection = Collection;
    exports.collectionFromPath = collectionFromPath;
    exports.isEmptyPath = isEmptyPath;
  }
});

// node_modules/yaml/dist/stringify/stringifyComment.js
var require_stringifyComment = __commonJS({
  "node_modules/yaml/dist/stringify/stringifyComment.js"(exports) {
    "use strict";
    var stringifyComment = (str) => str.replace(/^(?!$)(?: $)?/gm, "#");
    function indentComment(comment, indent) {
      if (/^\n+$/.test(comment))
        return comment.substring(1);
      return indent ? comment.replace(/^(?! *$)/gm, indent) : comment;
    }
    var lineComment = (str, indent, comment) => str.endsWith("\n") ? indentComment(comment, indent) : comment.includes("\n") ? "\n" + indentComment(comment, indent) : (str.endsWith(" ") ? "" : " ") + comment;
    exports.indentComment = indentComment;
    exports.lineComment = lineComment;
    exports.stringifyComment = stringifyComment;
  }
});

// node_modules/yaml/dist/stringify/foldFlowLines.js
var require_foldFlowLines = __commonJS({
  "node_modules/yaml/dist/stringify/foldFlowLines.js"(exports) {
    "use strict";
    var FOLD_FLOW = "flow";
    var FOLD_BLOCK = "block";
    var FOLD_QUOTED = "quoted";
    function foldFlowLines(text, indent, mode = "flow", { indentAtStart, lineWidth = 80, minContentWidth = 20, onFold, onOverflow } = {}) {
      if (!lineWidth || lineWidth < 0)
        return text;
      if (lineWidth < minContentWidth)
        minContentWidth = 0;
      const endStep = Math.max(1 + minContentWidth, 1 + lineWidth - indent.length);
      if (text.length <= endStep)
        return text;
      const folds = [];
      const escapedFolds = {};
      let end = lineWidth - indent.length;
      if (typeof indentAtStart === "number") {
        if (indentAtStart > lineWidth - Math.max(2, minContentWidth))
          folds.push(0);
        else
          end = lineWidth - indentAtStart;
      }
      let split = void 0;
      let prev = void 0;
      let overflow = false;
      let i = -1;
      let escStart = -1;
      let escEnd = -1;
      if (mode === FOLD_BLOCK) {
        i = consumeMoreIndentedLines(text, i, indent.length);
        if (i !== -1)
          end = i + endStep;
      }
      for (let ch; ch = text[i += 1]; ) {
        if (mode === FOLD_QUOTED && ch === "\\") {
          escStart = i;
          switch (text[i + 1]) {
            case "x":
              i += 3;
              break;
            case "u":
              i += 5;
              break;
            case "U":
              i += 9;
              break;
            default:
              i += 1;
          }
          escEnd = i;
        }
        if (ch === "\n") {
          if (mode === FOLD_BLOCK)
            i = consumeMoreIndentedLines(text, i, indent.length);
          end = i + indent.length + endStep;
          split = void 0;
        } else {
          if (ch === " " && prev && prev !== " " && prev !== "\n" && prev !== "	") {
            const next = text[i + 1];
            if (next && next !== " " && next !== "\n" && next !== "	")
              split = i;
          }
          if (i >= end) {
            if (split) {
              folds.push(split);
              end = split + endStep;
              split = void 0;
            } else if (mode === FOLD_QUOTED) {
              while (prev === " " || prev === "	") {
                prev = ch;
                ch = text[i += 1];
                overflow = true;
              }
              const j = i > escEnd + 1 ? i - 2 : escStart - 1;
              if (escapedFolds[j])
                return text;
              folds.push(j);
              escapedFolds[j] = true;
              end = j + endStep;
              split = void 0;
            } else {
              overflow = true;
            }
          }
        }
        prev = ch;
      }
      if (overflow && onOverflow)
        onOverflow();
      if (folds.length === 0)
        return text;
      if (onFold)
        onFold();
      let res = text.slice(0, folds[0]);
      for (let i2 = 0; i2 < folds.length; ++i2) {
        const fold3 = folds[i2];
        const end2 = folds[i2 + 1] || text.length;
        if (fold3 === 0)
          res = `
${indent}${text.slice(0, end2)}`;
        else {
          if (mode === FOLD_QUOTED && escapedFolds[fold3])
            res += `${text[fold3]}\\`;
          res += `
${indent}${text.slice(fold3 + 1, end2)}`;
        }
      }
      return res;
    }
    function consumeMoreIndentedLines(text, i, indent) {
      let end = i;
      let start = i + 1;
      let ch = text[start];
      while (ch === " " || ch === "	") {
        if (i < start + indent) {
          ch = text[++i];
        } else {
          do {
            ch = text[++i];
          } while (ch && ch !== "\n");
          end = i;
          start = i + 1;
          ch = text[start];
        }
      }
      return end;
    }
    exports.FOLD_BLOCK = FOLD_BLOCK;
    exports.FOLD_FLOW = FOLD_FLOW;
    exports.FOLD_QUOTED = FOLD_QUOTED;
    exports.foldFlowLines = foldFlowLines;
  }
});

// node_modules/yaml/dist/stringify/stringifyString.js
var require_stringifyString = __commonJS({
  "node_modules/yaml/dist/stringify/stringifyString.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var foldFlowLines = require_foldFlowLines();
    var getFoldOptions = (ctx, isBlock) => ({
      indentAtStart: isBlock ? ctx.indent.length : ctx.indentAtStart,
      lineWidth: ctx.options.lineWidth,
      minContentWidth: ctx.options.minContentWidth
    });
    var containsDocumentMarker = (str) => /^(%|---|\.\.\.)/m.test(str);
    function lineLengthOverLimit(str, lineWidth, indentLength) {
      if (!lineWidth || lineWidth < 0)
        return false;
      const limit = lineWidth - indentLength;
      const strLen = str.length;
      if (strLen <= limit)
        return false;
      for (let i = 0, start = 0; i < strLen; ++i) {
        if (str[i] === "\n") {
          if (i - start > limit)
            return true;
          start = i + 1;
          if (strLen - start <= limit)
            return false;
        }
      }
      return true;
    }
    function doubleQuotedString(value, ctx) {
      const json = JSON.stringify(value);
      if (ctx.options.doubleQuotedAsJSON)
        return json;
      const { implicitKey } = ctx;
      const minMultiLineLength = ctx.options.doubleQuotedMinMultiLineLength;
      const indent = ctx.indent || (containsDocumentMarker(value) ? "  " : "");
      let str = "";
      let start = 0;
      for (let i = 0, ch = json[i]; ch; ch = json[++i]) {
        if (ch === " " && json[i + 1] === "\\" && json[i + 2] === "n") {
          str += json.slice(start, i) + "\\ ";
          i += 1;
          start = i;
          ch = "\\";
        }
        if (ch === "\\")
          switch (json[i + 1]) {
            case "u":
              {
                str += json.slice(start, i);
                const code = json.substr(i + 2, 4);
                switch (code) {
                  case "0000":
                    str += "\\0";
                    break;
                  case "0007":
                    str += "\\a";
                    break;
                  case "000b":
                    str += "\\v";
                    break;
                  case "001b":
                    str += "\\e";
                    break;
                  case "0085":
                    str += "\\N";
                    break;
                  case "00a0":
                    str += "\\_";
                    break;
                  case "2028":
                    str += "\\L";
                    break;
                  case "2029":
                    str += "\\P";
                    break;
                  default:
                    if (code.substr(0, 2) === "00")
                      str += "\\x" + code.substr(2);
                    else
                      str += json.substr(i, 6);
                }
                i += 5;
                start = i + 1;
              }
              break;
            case "n":
              if (implicitKey || json[i + 2] === '"' || json.length < minMultiLineLength) {
                i += 1;
              } else {
                str += json.slice(start, i) + "\n\n";
                while (json[i + 2] === "\\" && json[i + 3] === "n" && json[i + 4] !== '"') {
                  str += "\n";
                  i += 2;
                }
                str += indent;
                if (json[i + 2] === " ")
                  str += "\\";
                i += 1;
                start = i + 1;
              }
              break;
            default:
              i += 1;
          }
      }
      str = start ? str + json.slice(start) : json;
      return implicitKey ? str : foldFlowLines.foldFlowLines(str, indent, foldFlowLines.FOLD_QUOTED, getFoldOptions(ctx, false));
    }
    function singleQuotedString(value, ctx) {
      if (ctx.options.singleQuote === false || ctx.implicitKey && value.includes("\n") || /[ \t]\n|\n[ \t]/.test(value))
        return doubleQuotedString(value, ctx);
      const indent = ctx.indent || (containsDocumentMarker(value) ? "  " : "");
      const res = "'" + value.replace(/'/g, "''").replace(/\n+/g, `$&
${indent}`) + "'";
      return ctx.implicitKey ? res : foldFlowLines.foldFlowLines(res, indent, foldFlowLines.FOLD_FLOW, getFoldOptions(ctx, false));
    }
    function quotedString(value, ctx) {
      const { singleQuote } = ctx.options;
      let qs;
      if (singleQuote === false)
        qs = doubleQuotedString;
      else {
        const hasDouble = value.includes('"');
        const hasSingle = value.includes("'");
        if (hasDouble && !hasSingle)
          qs = singleQuotedString;
        else if (hasSingle && !hasDouble)
          qs = doubleQuotedString;
        else
          qs = singleQuote ? singleQuotedString : doubleQuotedString;
      }
      return qs(value, ctx);
    }
    var blockEndNewlines;
    try {
      blockEndNewlines = new RegExp("(^|(?<!\n))\n+(?!\n|$)", "g");
    } catch {
      blockEndNewlines = /\n+(?!\n|$)/g;
    }
    function blockString({ comment, type, value }, ctx, onComment, onChompKeep) {
      const { blockQuote, commentString, lineWidth } = ctx.options;
      if (!blockQuote || /\n[\t ]+$/.test(value)) {
        return quotedString(value, ctx);
      }
      const indent = ctx.indent || (ctx.forceBlockIndent || containsDocumentMarker(value) ? "  " : "");
      const literal = blockQuote === "literal" ? true : blockQuote === "folded" || type === Scalar.Scalar.BLOCK_FOLDED ? false : type === Scalar.Scalar.BLOCK_LITERAL ? true : !lineLengthOverLimit(value, lineWidth, indent.length);
      if (!value)
        return literal ? "|\n" : ">\n";
      let chomp;
      let endStart;
      for (endStart = value.length; endStart > 0; --endStart) {
        const ch = value[endStart - 1];
        if (ch !== "\n" && ch !== "	" && ch !== " ")
          break;
      }
      let end = value.substring(endStart);
      const endNlPos = end.indexOf("\n");
      if (endNlPos === -1) {
        chomp = "-";
      } else if (value === end || endNlPos !== end.length - 1) {
        chomp = "+";
        if (onChompKeep)
          onChompKeep();
      } else {
        chomp = "";
      }
      if (end) {
        value = value.slice(0, -end.length);
        if (end[end.length - 1] === "\n")
          end = end.slice(0, -1);
        end = end.replace(blockEndNewlines, `$&${indent}`);
      }
      let startWithSpace = false;
      let startEnd;
      let startNlPos = -1;
      for (startEnd = 0; startEnd < value.length; ++startEnd) {
        const ch = value[startEnd];
        if (ch === " ")
          startWithSpace = true;
        else if (ch === "\n")
          startNlPos = startEnd;
        else
          break;
      }
      let start = value.substring(0, startNlPos < startEnd ? startNlPos + 1 : startEnd);
      if (start) {
        value = value.substring(start.length);
        start = start.replace(/\n+/g, `$&${indent}`);
      }
      const indentSize = indent ? "2" : "1";
      let header = (startWithSpace ? indentSize : "") + chomp;
      if (comment) {
        header += " " + commentString(comment.replace(/ ?[\r\n]+/g, " "));
        if (onComment)
          onComment();
      }
      if (!literal) {
        const foldedValue = value.replace(/\n+/g, "\n$&").replace(/(?:^|\n)([\t ].*)(?:([\n\t ]*)\n(?![\n\t ]))?/g, "$1$2").replace(/\n+/g, `$&${indent}`);
        let literalFallback = false;
        const foldOptions = getFoldOptions(ctx, true);
        if (blockQuote !== "folded" && type !== Scalar.Scalar.BLOCK_FOLDED) {
          foldOptions.onOverflow = () => {
            literalFallback = true;
          };
        }
        const body = foldFlowLines.foldFlowLines(`${start}${foldedValue}${end}`, indent, foldFlowLines.FOLD_BLOCK, foldOptions);
        if (!literalFallback)
          return `>${header}
${indent}${body}`;
      }
      value = value.replace(/\n+/g, `$&${indent}`);
      return `|${header}
${indent}${start}${value}${end}`;
    }
    function plainString(item, ctx, onComment, onChompKeep) {
      const { type, value } = item;
      const { actualString, implicitKey, indent, indentStep, inFlow } = ctx;
      if (implicitKey && value.includes("\n") || inFlow && /[[\]{},]/.test(value)) {
        return quotedString(value, ctx);
      }
      if (/^[\n\t ,[\]{}#&*!|>'"%@`]|^[?-]$|^[?-][ \t]|[\n:][ \t]|[ \t]\n|[\n\t ]#|[\n\t :]$/.test(value)) {
        return implicitKey || inFlow || !value.includes("\n") ? quotedString(value, ctx) : blockString(item, ctx, onComment, onChompKeep);
      }
      if (!implicitKey && !inFlow && type !== Scalar.Scalar.PLAIN && value.includes("\n")) {
        return blockString(item, ctx, onComment, onChompKeep);
      }
      if (containsDocumentMarker(value)) {
        if (indent === "") {
          ctx.forceBlockIndent = true;
          return blockString(item, ctx, onComment, onChompKeep);
        } else if (implicitKey && indent === indentStep) {
          return quotedString(value, ctx);
        }
      }
      const str = value.replace(/\n+/g, `$&
${indent}`);
      if (actualString) {
        const test = (tag) => tag.default && tag.tag !== "tag:yaml.org,2002:str" && tag.test?.test(str);
        const { compat, tags } = ctx.doc.schema;
        if (tags.some(test) || compat?.some(test))
          return quotedString(value, ctx);
      }
      return implicitKey ? str : foldFlowLines.foldFlowLines(str, indent, foldFlowLines.FOLD_FLOW, getFoldOptions(ctx, false));
    }
    function stringifyString(item, ctx, onComment, onChompKeep) {
      const { implicitKey, inFlow } = ctx;
      const ss = typeof item.value === "string" ? item : Object.assign({}, item, { value: String(item.value) });
      let { type } = item;
      if (type !== Scalar.Scalar.QUOTE_DOUBLE) {
        if (/[\x00-\x08\x0b-\x1f\x7f-\x9f\u{D800}-\u{DFFF}]/u.test(ss.value))
          type = Scalar.Scalar.QUOTE_DOUBLE;
      }
      const _stringify = (_type) => {
        switch (_type) {
          case Scalar.Scalar.BLOCK_FOLDED:
          case Scalar.Scalar.BLOCK_LITERAL:
            return implicitKey || inFlow ? quotedString(ss.value, ctx) : blockString(ss, ctx, onComment, onChompKeep);
          case Scalar.Scalar.QUOTE_DOUBLE:
            return doubleQuotedString(ss.value, ctx);
          case Scalar.Scalar.QUOTE_SINGLE:
            return singleQuotedString(ss.value, ctx);
          case Scalar.Scalar.PLAIN:
            return plainString(ss, ctx, onComment, onChompKeep);
          default:
            return null;
        }
      };
      let res = _stringify(type);
      if (res === null) {
        const { defaultKeyType, defaultStringType } = ctx.options;
        const t = implicitKey && defaultKeyType || defaultStringType;
        res = _stringify(t);
        if (res === null)
          throw new Error(`Unsupported default string type ${t}`);
      }
      return res;
    }
    exports.stringifyString = stringifyString;
  }
});

// node_modules/yaml/dist/stringify/stringify.js
var require_stringify = __commonJS({
  "node_modules/yaml/dist/stringify/stringify.js"(exports) {
    "use strict";
    var anchors = require_anchors();
    var identity = require_identity();
    var stringifyComment = require_stringifyComment();
    var stringifyString = require_stringifyString();
    function createStringifyContext(doc, options) {
      const opt = Object.assign({
        blockQuote: true,
        commentString: stringifyComment.stringifyComment,
        defaultKeyType: null,
        defaultStringType: "PLAIN",
        directives: null,
        doubleQuotedAsJSON: false,
        doubleQuotedMinMultiLineLength: 40,
        falseStr: "false",
        flowCollectionPadding: true,
        indentSeq: true,
        lineWidth: 80,
        minContentWidth: 20,
        nullStr: "null",
        simpleKeys: false,
        singleQuote: null,
        trailingComma: false,
        trueStr: "true",
        verifyAliasOrder: true
      }, doc.schema.toStringOptions, options);
      let inFlow;
      switch (opt.collectionStyle) {
        case "block":
          inFlow = false;
          break;
        case "flow":
          inFlow = true;
          break;
        default:
          inFlow = null;
      }
      return {
        anchors: /* @__PURE__ */ new Set(),
        doc,
        flowCollectionPadding: opt.flowCollectionPadding ? " " : "",
        indent: "",
        indentStep: typeof opt.indent === "number" ? " ".repeat(opt.indent) : "  ",
        inFlow,
        options: opt
      };
    }
    function getTagObject(tags, item) {
      if (item.tag) {
        const match2 = tags.filter((t) => t.tag === item.tag);
        if (match2.length > 0)
          return match2.find((t) => t.format === item.format) ?? match2[0];
      }
      let tagObj = void 0;
      let obj;
      if (identity.isScalar(item)) {
        obj = item.value;
        let match2 = tags.filter((t) => t.identify?.(obj));
        if (match2.length > 1) {
          const testMatch = match2.filter((t) => t.test);
          if (testMatch.length > 0)
            match2 = testMatch;
        }
        tagObj = match2.find((t) => t.format === item.format) ?? match2.find((t) => !t.format);
      } else {
        obj = item;
        tagObj = tags.find((t) => t.nodeClass && obj instanceof t.nodeClass);
      }
      if (!tagObj) {
        const name = obj?.constructor?.name ?? (obj === null ? "null" : typeof obj);
        throw new Error(`Tag not resolved for ${name} value`);
      }
      return tagObj;
    }
    function stringifyProps(node, tagObj, { anchors: anchors$1, doc }) {
      if (!doc.directives)
        return "";
      const props = [];
      const anchor = (identity.isScalar(node) || identity.isCollection(node)) && node.anchor;
      if (anchor && anchors.anchorIsValid(anchor)) {
        anchors$1.add(anchor);
        props.push(`&${anchor}`);
      }
      const tag = node.tag ?? (tagObj.default ? null : tagObj.tag);
      if (tag)
        props.push(doc.directives.tagString(tag));
      return props.join(" ");
    }
    function stringify(item, ctx, onComment, onChompKeep) {
      if (identity.isPair(item))
        return item.toString(ctx, onComment, onChompKeep);
      if (identity.isAlias(item)) {
        if (ctx.doc.directives)
          return item.toString(ctx);
        if (ctx.resolvedAliases?.has(item)) {
          throw new TypeError(`Cannot stringify circular structure without alias nodes`);
        } else {
          if (ctx.resolvedAliases)
            ctx.resolvedAliases.add(item);
          else
            ctx.resolvedAliases = /* @__PURE__ */ new Set([item]);
          item = item.resolve(ctx.doc);
        }
      }
      let tagObj = void 0;
      const node = identity.isNode(item) ? item : ctx.doc.createNode(item, { onTagObj: (o) => tagObj = o });
      tagObj ?? (tagObj = getTagObject(ctx.doc.schema.tags, node));
      const props = stringifyProps(node, tagObj, ctx);
      if (props.length > 0)
        ctx.indentAtStart = (ctx.indentAtStart ?? 0) + props.length + 1;
      const str = typeof tagObj.stringify === "function" ? tagObj.stringify(node, ctx, onComment, onChompKeep) : identity.isScalar(node) ? stringifyString.stringifyString(node, ctx, onComment, onChompKeep) : node.toString(ctx, onComment, onChompKeep);
      if (!props)
        return str;
      return identity.isScalar(node) || str[0] === "{" || str[0] === "[" ? `${props} ${str}` : `${props}
${ctx.indent}${str}`;
    }
    exports.createStringifyContext = createStringifyContext;
    exports.stringify = stringify;
  }
});

// node_modules/yaml/dist/stringify/stringifyPair.js
var require_stringifyPair = __commonJS({
  "node_modules/yaml/dist/stringify/stringifyPair.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var stringify = require_stringify();
    var stringifyComment = require_stringifyComment();
    function stringifyPair({ key, value }, ctx, onComment, onChompKeep) {
      const { allNullValues, doc, indent, indentStep, options: { commentString, indentSeq, simpleKeys } } = ctx;
      let keyComment = identity.isNode(key) && key.comment || null;
      if (simpleKeys) {
        if (keyComment) {
          throw new Error("With simple keys, key nodes cannot have comments");
        }
        if (identity.isCollection(key) || !identity.isNode(key) && typeof key === "object") {
          const msg = "With simple keys, collection cannot be used as a key value";
          throw new Error(msg);
        }
      }
      let explicitKey = !simpleKeys && (!key || keyComment && value == null && !ctx.inFlow || identity.isCollection(key) || (identity.isScalar(key) ? key.type === Scalar.Scalar.BLOCK_FOLDED || key.type === Scalar.Scalar.BLOCK_LITERAL : typeof key === "object"));
      ctx = Object.assign({}, ctx, {
        allNullValues: false,
        implicitKey: !explicitKey && (simpleKeys || !allNullValues),
        indent: indent + indentStep
      });
      let keyCommentDone = false;
      let chompKeep = false;
      let str = stringify.stringify(key, ctx, () => keyCommentDone = true, () => chompKeep = true);
      if (!explicitKey && !ctx.inFlow && str.length > 1024) {
        if (simpleKeys)
          throw new Error("With simple keys, single line scalar must not span more than 1024 characters");
        explicitKey = true;
      }
      if (ctx.inFlow) {
        if (allNullValues || value == null) {
          if (keyCommentDone && onComment)
            onComment();
          return str === "" ? "?" : explicitKey ? `? ${str}` : str;
        }
      } else if (allNullValues && !simpleKeys || value == null && explicitKey) {
        str = `? ${str}`;
        if (keyComment && !keyCommentDone) {
          str += stringifyComment.lineComment(str, ctx.indent, commentString(keyComment));
        } else if (chompKeep && onChompKeep)
          onChompKeep();
        return str;
      }
      if (keyCommentDone)
        keyComment = null;
      if (explicitKey) {
        if (keyComment)
          str += stringifyComment.lineComment(str, ctx.indent, commentString(keyComment));
        str = `? ${str}
${indent}:`;
      } else {
        str = `${str}:`;
        if (keyComment)
          str += stringifyComment.lineComment(str, ctx.indent, commentString(keyComment));
      }
      let vsb, vcb, valueComment;
      if (identity.isNode(value)) {
        vsb = !!value.spaceBefore;
        vcb = value.commentBefore;
        valueComment = value.comment;
      } else {
        vsb = false;
        vcb = null;
        valueComment = null;
        if (value && typeof value === "object")
          value = doc.createNode(value);
      }
      ctx.implicitKey = false;
      if (!explicitKey && !keyComment && identity.isScalar(value))
        ctx.indentAtStart = str.length + 1;
      chompKeep = false;
      if (!indentSeq && indentStep.length >= 2 && !ctx.inFlow && !explicitKey && identity.isSeq(value) && !value.flow && !value.tag && !value.anchor) {
        ctx.indent = ctx.indent.substring(2);
      }
      let valueCommentDone = false;
      const valueStr = stringify.stringify(value, ctx, () => valueCommentDone = true, () => chompKeep = true);
      let ws = " ";
      if (keyComment || vsb || vcb) {
        ws = vsb ? "\n" : "";
        if (vcb) {
          const cs = commentString(vcb);
          ws += `
${stringifyComment.indentComment(cs, ctx.indent)}`;
        }
        if (valueStr === "" && !ctx.inFlow) {
          if (ws === "\n" && valueComment)
            ws = "\n\n";
        } else {
          ws += `
${ctx.indent}`;
        }
      } else if (!explicitKey && identity.isCollection(value)) {
        const vs0 = valueStr[0];
        const nl0 = valueStr.indexOf("\n");
        const hasNewline = nl0 !== -1;
        const flow = ctx.inFlow ?? value.flow ?? value.items.length === 0;
        if (hasNewline || !flow) {
          let hasPropsLine = false;
          if (hasNewline && (vs0 === "&" || vs0 === "!")) {
            let sp0 = valueStr.indexOf(" ");
            if (vs0 === "&" && sp0 !== -1 && sp0 < nl0 && valueStr[sp0 + 1] === "!") {
              sp0 = valueStr.indexOf(" ", sp0 + 1);
            }
            if (sp0 === -1 || nl0 < sp0)
              hasPropsLine = true;
          }
          if (!hasPropsLine)
            ws = `
${ctx.indent}`;
        }
      } else if (valueStr === "" || valueStr[0] === "\n") {
        ws = "";
      }
      str += ws + valueStr;
      if (ctx.inFlow) {
        if (valueCommentDone && onComment)
          onComment();
      } else if (valueComment && !valueCommentDone) {
        str += stringifyComment.lineComment(str, ctx.indent, commentString(valueComment));
      } else if (chompKeep && onChompKeep) {
        onChompKeep();
      }
      return str;
    }
    exports.stringifyPair = stringifyPair;
  }
});

// node_modules/yaml/dist/log.js
var require_log = __commonJS({
  "node_modules/yaml/dist/log.js"(exports) {
    "use strict";
    var node_process = __require("process");
    function debug(logLevel, ...messages) {
      if (logLevel === "debug")
        console.log(...messages);
    }
    function warn(logLevel, warning) {
      if (logLevel === "debug" || logLevel === "warn") {
        if (typeof node_process.emitWarning === "function")
          node_process.emitWarning(warning);
        else
          console.warn(warning);
      }
    }
    exports.debug = debug;
    exports.warn = warn;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/merge.js
var require_merge = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/merge.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var MERGE_KEY = "<<";
    var merge = {
      identify: (value) => value === MERGE_KEY || typeof value === "symbol" && value.description === MERGE_KEY,
      default: "key",
      tag: "tag:yaml.org,2002:merge",
      test: /^<<$/,
      resolve: () => Object.assign(new Scalar.Scalar(Symbol(MERGE_KEY)), {
        addToJSMap: addMergeToJSMap
      }),
      stringify: () => MERGE_KEY
    };
    var isMergeKey = (ctx, key) => (merge.identify(key) || identity.isScalar(key) && (!key.type || key.type === Scalar.Scalar.PLAIN) && merge.identify(key.value)) && ctx?.doc.schema.tags.some((tag) => tag.tag === merge.tag && tag.default);
    function addMergeToJSMap(ctx, map, value) {
      const source = resolveAliasValue(ctx, value);
      if (identity.isSeq(source))
        for (const it of source.items)
          mergeValue(ctx, map, it);
      else if (Array.isArray(source))
        for (const it of source)
          mergeValue(ctx, map, it);
      else
        mergeValue(ctx, map, source);
    }
    function mergeValue(ctx, map, value) {
      const source = resolveAliasValue(ctx, value);
      if (!identity.isMap(source))
        throw new Error("Merge sources must be maps or map aliases");
      const srcMap = source.toJSON(null, ctx, Map);
      for (const [key, value2] of srcMap) {
        if (map instanceof Map) {
          if (!map.has(key))
            map.set(key, value2);
        } else if (map instanceof Set) {
          map.add(key);
        } else if (!Object.prototype.hasOwnProperty.call(map, key)) {
          Object.defineProperty(map, key, {
            value: value2,
            writable: true,
            enumerable: true,
            configurable: true
          });
        }
      }
      return map;
    }
    function resolveAliasValue(ctx, value) {
      return ctx && identity.isAlias(value) ? value.resolve(ctx.doc, ctx) : value;
    }
    exports.addMergeToJSMap = addMergeToJSMap;
    exports.isMergeKey = isMergeKey;
    exports.merge = merge;
  }
});

// node_modules/yaml/dist/nodes/addPairToJSMap.js
var require_addPairToJSMap = __commonJS({
  "node_modules/yaml/dist/nodes/addPairToJSMap.js"(exports) {
    "use strict";
    var log = require_log();
    var merge = require_merge();
    var stringify = require_stringify();
    var identity = require_identity();
    var toJS = require_toJS();
    function addPairToJSMap(ctx, map, { key, value }) {
      if (identity.isNode(key) && key.addToJSMap)
        key.addToJSMap(ctx, map, value);
      else if (merge.isMergeKey(ctx, key))
        merge.addMergeToJSMap(ctx, map, value);
      else {
        const jsKey = toJS.toJS(key, "", ctx);
        if (map instanceof Map) {
          map.set(jsKey, toJS.toJS(value, jsKey, ctx));
        } else if (map instanceof Set) {
          map.add(jsKey);
        } else {
          const stringKey = stringifyKey(key, jsKey, ctx);
          const jsValue = toJS.toJS(value, stringKey, ctx);
          if (stringKey in map)
            Object.defineProperty(map, stringKey, {
              value: jsValue,
              writable: true,
              enumerable: true,
              configurable: true
            });
          else
            map[stringKey] = jsValue;
        }
      }
      return map;
    }
    function stringifyKey(key, jsKey, ctx) {
      if (jsKey === null)
        return "";
      if (typeof jsKey !== "object")
        return String(jsKey);
      if (identity.isNode(key) && ctx?.doc) {
        const strCtx = stringify.createStringifyContext(ctx.doc, {});
        strCtx.anchors = /* @__PURE__ */ new Set();
        for (const node of ctx.anchors.keys())
          strCtx.anchors.add(node.anchor);
        strCtx.inFlow = true;
        strCtx.inStringifyKey = true;
        const strKey = key.toString(strCtx);
        if (!ctx.mapKeyWarned) {
          let jsonStr = JSON.stringify(strKey);
          if (jsonStr.length > 40)
            jsonStr = jsonStr.substring(0, 36) + '..."';
          log.warn(ctx.doc.options.logLevel, `Keys with collection values will be stringified due to JS Object restrictions: ${jsonStr}. Set mapAsMap: true to use object keys.`);
          ctx.mapKeyWarned = true;
        }
        return strKey;
      }
      return JSON.stringify(jsKey);
    }
    exports.addPairToJSMap = addPairToJSMap;
  }
});

// node_modules/yaml/dist/nodes/Pair.js
var require_Pair = __commonJS({
  "node_modules/yaml/dist/nodes/Pair.js"(exports) {
    "use strict";
    var createNode = require_createNode();
    var stringifyPair = require_stringifyPair();
    var addPairToJSMap = require_addPairToJSMap();
    var identity = require_identity();
    function createPair(key, value, ctx) {
      const k = createNode.createNode(key, void 0, ctx);
      const v = createNode.createNode(value, void 0, ctx);
      return new Pair(k, v);
    }
    var Pair = class _Pair {
      constructor(key, value = null) {
        Object.defineProperty(this, identity.NODE_TYPE, { value: identity.PAIR });
        this.key = key;
        this.value = value;
      }
      clone(schema) {
        let { key, value } = this;
        if (identity.isNode(key))
          key = key.clone(schema);
        if (identity.isNode(value))
          value = value.clone(schema);
        return new _Pair(key, value);
      }
      toJSON(_, ctx) {
        const pair = ctx?.mapAsMap ? /* @__PURE__ */ new Map() : {};
        return addPairToJSMap.addPairToJSMap(ctx, pair, this);
      }
      toString(ctx, onComment, onChompKeep) {
        return ctx?.doc ? stringifyPair.stringifyPair(this, ctx, onComment, onChompKeep) : JSON.stringify(this);
      }
    };
    exports.Pair = Pair;
    exports.createPair = createPair;
  }
});

// node_modules/yaml/dist/stringify/stringifyCollection.js
var require_stringifyCollection = __commonJS({
  "node_modules/yaml/dist/stringify/stringifyCollection.js"(exports) {
    "use strict";
    var identity = require_identity();
    var stringify = require_stringify();
    var stringifyComment = require_stringifyComment();
    function stringifyCollection(collection, ctx, options) {
      const flow = ctx.inFlow ?? collection.flow;
      const stringify2 = flow ? stringifyFlowCollection : stringifyBlockCollection;
      return stringify2(collection, ctx, options);
    }
    function stringifyBlockCollection({ comment, items }, ctx, { blockItemPrefix, flowChars, itemIndent, onChompKeep, onComment }) {
      const { indent, options: { commentString } } = ctx;
      const itemCtx = Object.assign({}, ctx, { indent: itemIndent, type: null });
      let chompKeep = false;
      const lines = [];
      for (let i = 0; i < items.length; ++i) {
        const item = items[i];
        let comment2 = null;
        if (identity.isNode(item)) {
          if (!chompKeep && item.spaceBefore)
            lines.push("");
          addCommentBefore(ctx, lines, item.commentBefore, chompKeep);
          if (item.comment)
            comment2 = item.comment;
        } else if (identity.isPair(item)) {
          const ik = identity.isNode(item.key) ? item.key : null;
          if (ik) {
            if (!chompKeep && ik.spaceBefore)
              lines.push("");
            addCommentBefore(ctx, lines, ik.commentBefore, chompKeep);
          }
        }
        chompKeep = false;
        let str2 = stringify.stringify(item, itemCtx, () => comment2 = null, () => chompKeep = true);
        if (comment2)
          str2 += stringifyComment.lineComment(str2, itemIndent, commentString(comment2));
        if (chompKeep && comment2)
          chompKeep = false;
        lines.push(blockItemPrefix + str2);
      }
      let str;
      if (lines.length === 0) {
        str = flowChars.start + flowChars.end;
      } else {
        str = lines[0];
        for (let i = 1; i < lines.length; ++i) {
          const line = lines[i];
          str += line ? `
${indent}${line}` : "\n";
        }
      }
      if (comment) {
        str += "\n" + stringifyComment.indentComment(commentString(comment), indent);
        if (onComment)
          onComment();
      } else if (chompKeep && onChompKeep)
        onChompKeep();
      return str;
    }
    function stringifyFlowCollection({ items }, ctx, { flowChars, itemIndent }) {
      const { indent, indentStep, flowCollectionPadding: fcPadding, options: { commentString } } = ctx;
      itemIndent += indentStep;
      const itemCtx = Object.assign({}, ctx, {
        indent: itemIndent,
        inFlow: true,
        type: null
      });
      let reqNewline = false;
      let linesAtValue = 0;
      const lines = [];
      for (let i = 0; i < items.length; ++i) {
        const item = items[i];
        let comment = null;
        if (identity.isNode(item)) {
          if (item.spaceBefore)
            lines.push("");
          addCommentBefore(ctx, lines, item.commentBefore, false);
          if (item.comment)
            comment = item.comment;
        } else if (identity.isPair(item)) {
          const ik = identity.isNode(item.key) ? item.key : null;
          if (ik) {
            if (ik.spaceBefore)
              lines.push("");
            addCommentBefore(ctx, lines, ik.commentBefore, false);
            if (ik.comment)
              reqNewline = true;
          }
          const iv = identity.isNode(item.value) ? item.value : null;
          if (iv) {
            if (iv.comment)
              comment = iv.comment;
            if (iv.commentBefore)
              reqNewline = true;
          } else if (item.value == null && ik?.comment) {
            comment = ik.comment;
          }
        }
        if (comment)
          reqNewline = true;
        let str = stringify.stringify(item, itemCtx, () => comment = null);
        reqNewline || (reqNewline = lines.length > linesAtValue || str.includes("\n"));
        if (i < items.length - 1) {
          str += ",";
        } else if (ctx.options.trailingComma) {
          if (ctx.options.lineWidth > 0) {
            reqNewline || (reqNewline = lines.reduce((sum, line) => sum + line.length + 2, 2) + (str.length + 2) > ctx.options.lineWidth);
          }
          if (reqNewline) {
            str += ",";
          }
        }
        if (comment)
          str += stringifyComment.lineComment(str, itemIndent, commentString(comment));
        lines.push(str);
        linesAtValue = lines.length;
      }
      const { start, end } = flowChars;
      if (lines.length === 0) {
        return start + end;
      } else {
        if (!reqNewline) {
          const len = lines.reduce((sum, line) => sum + line.length + 2, 2);
          reqNewline = ctx.options.lineWidth > 0 && len > ctx.options.lineWidth;
        }
        if (reqNewline) {
          let str = start;
          for (const line of lines)
            str += line ? `
${indentStep}${indent}${line}` : "\n";
          return `${str}
${indent}${end}`;
        } else {
          return `${start}${fcPadding}${lines.join(" ")}${fcPadding}${end}`;
        }
      }
    }
    function addCommentBefore({ indent, options: { commentString } }, lines, comment, chompKeep) {
      if (comment && chompKeep)
        comment = comment.replace(/^\n+/, "");
      if (comment) {
        const ic = stringifyComment.indentComment(commentString(comment), indent);
        lines.push(ic.trimStart());
      }
    }
    exports.stringifyCollection = stringifyCollection;
  }
});

// node_modules/yaml/dist/nodes/YAMLMap.js
var require_YAMLMap = __commonJS({
  "node_modules/yaml/dist/nodes/YAMLMap.js"(exports) {
    "use strict";
    var stringifyCollection = require_stringifyCollection();
    var addPairToJSMap = require_addPairToJSMap();
    var Collection = require_Collection();
    var identity = require_identity();
    var Pair = require_Pair();
    var Scalar = require_Scalar();
    function findPair(items, key) {
      const k = identity.isScalar(key) ? key.value : key;
      for (const it of items) {
        if (identity.isPair(it)) {
          if (it.key === key || it.key === k)
            return it;
          if (identity.isScalar(it.key) && it.key.value === k)
            return it;
        }
      }
      return void 0;
    }
    var YAMLMap = class extends Collection.Collection {
      static get tagName() {
        return "tag:yaml.org,2002:map";
      }
      constructor(schema) {
        super(identity.MAP, schema);
        this.items = [];
      }
      /**
       * A generic collection parsing method that can be extended
       * to other node classes that inherit from YAMLMap
       */
      static from(schema, obj, ctx) {
        const { keepUndefined, replacer } = ctx;
        const map = new this(schema);
        const add = (key, value) => {
          if (typeof replacer === "function")
            value = replacer.call(obj, key, value);
          else if (Array.isArray(replacer) && !replacer.includes(key))
            return;
          if (value !== void 0 || keepUndefined)
            map.items.push(Pair.createPair(key, value, ctx));
        };
        if (obj instanceof Map) {
          for (const [key, value] of obj)
            add(key, value);
        } else if (obj && typeof obj === "object") {
          for (const key of Object.keys(obj))
            add(key, obj[key]);
        }
        if (typeof schema.sortMapEntries === "function") {
          map.items.sort(schema.sortMapEntries);
        }
        return map;
      }
      /**
       * Adds a value to the collection.
       *
       * @param overwrite - If not set `true`, using a key that is already in the
       *   collection will throw. Otherwise, overwrites the previous value.
       */
      add(pair, overwrite) {
        let _pair;
        if (identity.isPair(pair))
          _pair = pair;
        else if (!pair || typeof pair !== "object" || !("key" in pair)) {
          _pair = new Pair.Pair(pair, pair?.value);
        } else
          _pair = new Pair.Pair(pair.key, pair.value);
        const prev = findPair(this.items, _pair.key);
        const sortEntries = this.schema?.sortMapEntries;
        if (prev) {
          if (!overwrite)
            throw new Error(`Key ${_pair.key} already set`);
          if (identity.isScalar(prev.value) && Scalar.isScalarValue(_pair.value))
            prev.value.value = _pair.value;
          else
            prev.value = _pair.value;
        } else if (sortEntries) {
          const i = this.items.findIndex((item) => sortEntries(_pair, item) < 0);
          if (i === -1)
            this.items.push(_pair);
          else
            this.items.splice(i, 0, _pair);
        } else {
          this.items.push(_pair);
        }
      }
      delete(key) {
        const it = findPair(this.items, key);
        if (!it)
          return false;
        const del = this.items.splice(this.items.indexOf(it), 1);
        return del.length > 0;
      }
      get(key, keepScalar) {
        const it = findPair(this.items, key);
        const node = it?.value;
        return (!keepScalar && identity.isScalar(node) ? node.value : node) ?? void 0;
      }
      has(key) {
        return !!findPair(this.items, key);
      }
      set(key, value) {
        this.add(new Pair.Pair(key, value), true);
      }
      /**
       * @param ctx - Conversion context, originally set in Document#toJS()
       * @param {Class} Type - If set, forces the returned collection type
       * @returns Instance of Type, Map, or Object
       */
      toJSON(_, ctx, Type2) {
        const map = Type2 ? new Type2() : ctx?.mapAsMap ? /* @__PURE__ */ new Map() : {};
        if (ctx?.onCreate)
          ctx.onCreate(map);
        for (const item of this.items)
          addPairToJSMap.addPairToJSMap(ctx, map, item);
        return map;
      }
      toString(ctx, onComment, onChompKeep) {
        if (!ctx)
          return JSON.stringify(this);
        for (const item of this.items) {
          if (!identity.isPair(item))
            throw new Error(`Map items must all be pairs; found ${JSON.stringify(item)} instead`);
        }
        if (!ctx.allNullValues && this.hasAllNullValues(false))
          ctx = Object.assign({}, ctx, { allNullValues: true });
        return stringifyCollection.stringifyCollection(this, ctx, {
          blockItemPrefix: "",
          flowChars: { start: "{", end: "}" },
          itemIndent: ctx.indent || "",
          onChompKeep,
          onComment
        });
      }
    };
    exports.YAMLMap = YAMLMap;
    exports.findPair = findPair;
  }
});

// node_modules/yaml/dist/schema/common/map.js
var require_map = __commonJS({
  "node_modules/yaml/dist/schema/common/map.js"(exports) {
    "use strict";
    var identity = require_identity();
    var YAMLMap = require_YAMLMap();
    var map = {
      collection: "map",
      default: true,
      nodeClass: YAMLMap.YAMLMap,
      tag: "tag:yaml.org,2002:map",
      resolve(map2, onError) {
        if (!identity.isMap(map2))
          onError("Expected a mapping for this tag");
        return map2;
      },
      createNode: (schema, obj, ctx) => YAMLMap.YAMLMap.from(schema, obj, ctx)
    };
    exports.map = map;
  }
});

// node_modules/yaml/dist/nodes/YAMLSeq.js
var require_YAMLSeq = __commonJS({
  "node_modules/yaml/dist/nodes/YAMLSeq.js"(exports) {
    "use strict";
    var createNode = require_createNode();
    var stringifyCollection = require_stringifyCollection();
    var Collection = require_Collection();
    var identity = require_identity();
    var Scalar = require_Scalar();
    var toJS = require_toJS();
    var YAMLSeq = class extends Collection.Collection {
      static get tagName() {
        return "tag:yaml.org,2002:seq";
      }
      constructor(schema) {
        super(identity.SEQ, schema);
        this.items = [];
      }
      add(value) {
        this.items.push(value);
      }
      /**
       * Removes a value from the collection.
       *
       * `key` must contain a representation of an integer for this to succeed.
       * It may be wrapped in a `Scalar`.
       *
       * @returns `true` if the item was found and removed.
       */
      delete(key) {
        const idx = asItemIndex(key);
        if (typeof idx !== "number")
          return false;
        const del = this.items.splice(idx, 1);
        return del.length > 0;
      }
      get(key, keepScalar) {
        const idx = asItemIndex(key);
        if (typeof idx !== "number")
          return void 0;
        const it = this.items[idx];
        return !keepScalar && identity.isScalar(it) ? it.value : it;
      }
      /**
       * Checks if the collection includes a value with the key `key`.
       *
       * `key` must contain a representation of an integer for this to succeed.
       * It may be wrapped in a `Scalar`.
       */
      has(key) {
        const idx = asItemIndex(key);
        return typeof idx === "number" && idx < this.items.length;
      }
      /**
       * Sets a value in this collection. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       *
       * If `key` does not contain a representation of an integer, this will throw.
       * It may be wrapped in a `Scalar`.
       */
      set(key, value) {
        const idx = asItemIndex(key);
        if (typeof idx !== "number")
          throw new Error(`Expected a valid index, not ${key}.`);
        const prev = this.items[idx];
        if (identity.isScalar(prev) && Scalar.isScalarValue(value))
          prev.value = value;
        else
          this.items[idx] = value;
      }
      toJSON(_, ctx) {
        const seq = [];
        if (ctx?.onCreate)
          ctx.onCreate(seq);
        let i = 0;
        for (const item of this.items)
          seq.push(toJS.toJS(item, String(i++), ctx));
        return seq;
      }
      toString(ctx, onComment, onChompKeep) {
        if (!ctx)
          return JSON.stringify(this);
        return stringifyCollection.stringifyCollection(this, ctx, {
          blockItemPrefix: "- ",
          flowChars: { start: "[", end: "]" },
          itemIndent: (ctx.indent || "") + "  ",
          onChompKeep,
          onComment
        });
      }
      static from(schema, obj, ctx) {
        const { replacer } = ctx;
        const seq = new this(schema);
        if (obj && Symbol.iterator in Object(obj)) {
          let i = 0;
          for (let it of obj) {
            if (typeof replacer === "function") {
              const key = obj instanceof Set ? it : String(i++);
              it = replacer.call(obj, key, it);
            }
            seq.items.push(createNode.createNode(it, void 0, ctx));
          }
        }
        return seq;
      }
    };
    function asItemIndex(key) {
      let idx = identity.isScalar(key) ? key.value : key;
      if (idx && typeof idx === "string")
        idx = Number(idx);
      return typeof idx === "number" && Number.isInteger(idx) && idx >= 0 ? idx : null;
    }
    exports.YAMLSeq = YAMLSeq;
  }
});

// node_modules/yaml/dist/schema/common/seq.js
var require_seq = __commonJS({
  "node_modules/yaml/dist/schema/common/seq.js"(exports) {
    "use strict";
    var identity = require_identity();
    var YAMLSeq = require_YAMLSeq();
    var seq = {
      collection: "seq",
      default: true,
      nodeClass: YAMLSeq.YAMLSeq,
      tag: "tag:yaml.org,2002:seq",
      resolve(seq2, onError) {
        if (!identity.isSeq(seq2))
          onError("Expected a sequence for this tag");
        return seq2;
      },
      createNode: (schema, obj, ctx) => YAMLSeq.YAMLSeq.from(schema, obj, ctx)
    };
    exports.seq = seq;
  }
});

// node_modules/yaml/dist/schema/common/string.js
var require_string = __commonJS({
  "node_modules/yaml/dist/schema/common/string.js"(exports) {
    "use strict";
    var stringifyString = require_stringifyString();
    var string = {
      identify: (value) => typeof value === "string",
      default: true,
      tag: "tag:yaml.org,2002:str",
      resolve: (str) => str,
      stringify(item, ctx, onComment, onChompKeep) {
        ctx = Object.assign({ actualString: true }, ctx);
        return stringifyString.stringifyString(item, ctx, onComment, onChompKeep);
      }
    };
    exports.string = string;
  }
});

// node_modules/yaml/dist/schema/common/null.js
var require_null = __commonJS({
  "node_modules/yaml/dist/schema/common/null.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var nullTag = {
      identify: (value) => value == null,
      createNode: () => new Scalar.Scalar(null),
      default: true,
      tag: "tag:yaml.org,2002:null",
      test: /^(?:~|[Nn]ull|NULL)?$/,
      resolve: () => new Scalar.Scalar(null),
      stringify: ({ source }, ctx) => typeof source === "string" && nullTag.test.test(source) ? source : ctx.options.nullStr
    };
    exports.nullTag = nullTag;
  }
});

// node_modules/yaml/dist/schema/core/bool.js
var require_bool = __commonJS({
  "node_modules/yaml/dist/schema/core/bool.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var boolTag = {
      identify: (value) => typeof value === "boolean",
      default: true,
      tag: "tag:yaml.org,2002:bool",
      test: /^(?:[Tt]rue|TRUE|[Ff]alse|FALSE)$/,
      resolve: (str) => new Scalar.Scalar(str[0] === "t" || str[0] === "T"),
      stringify({ source, value }, ctx) {
        if (source && boolTag.test.test(source)) {
          const sv = source[0] === "t" || source[0] === "T";
          if (value === sv)
            return source;
        }
        return value ? ctx.options.trueStr : ctx.options.falseStr;
      }
    };
    exports.boolTag = boolTag;
  }
});

// node_modules/yaml/dist/stringify/stringifyNumber.js
var require_stringifyNumber = __commonJS({
  "node_modules/yaml/dist/stringify/stringifyNumber.js"(exports) {
    "use strict";
    function stringifyNumber({ format, minFractionDigits, tag, value }) {
      if (typeof value === "bigint")
        return String(value);
      const num = typeof value === "number" ? value : Number(value);
      if (!isFinite(num))
        return isNaN(num) ? ".nan" : num < 0 ? "-.inf" : ".inf";
      let n = Object.is(value, -0) ? "-0" : JSON.stringify(value);
      if (!format && minFractionDigits && (!tag || tag === "tag:yaml.org,2002:float") && /^-?\d/.test(n) && !n.includes("e")) {
        let i = n.indexOf(".");
        if (i < 0) {
          i = n.length;
          n += ".";
        }
        let d = minFractionDigits - (n.length - i - 1);
        while (d-- > 0)
          n += "0";
      }
      return n;
    }
    exports.stringifyNumber = stringifyNumber;
  }
});

// node_modules/yaml/dist/schema/core/float.js
var require_float = __commonJS({
  "node_modules/yaml/dist/schema/core/float.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var stringifyNumber = require_stringifyNumber();
    var floatNaN = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^(?:[-+]?\.(?:inf|Inf|INF)|\.nan|\.NaN|\.NAN)$/,
      resolve: (str) => str.slice(-3).toLowerCase() === "nan" ? NaN : str[0] === "-" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY,
      stringify: stringifyNumber.stringifyNumber
    };
    var floatExp = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      format: "EXP",
      test: /^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)[eE][-+]?[0-9]+$/,
      resolve: (str) => parseFloat(str),
      stringify(node) {
        const num = Number(node.value);
        return isFinite(num) ? num.toExponential() : stringifyNumber.stringifyNumber(node);
      }
    };
    var float = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^[-+]?(?:\.[0-9]+|[0-9]+\.[0-9]*)$/,
      resolve(str) {
        const node = new Scalar.Scalar(parseFloat(str));
        const dot = str.indexOf(".");
        if (dot !== -1 && str[str.length - 1] === "0")
          node.minFractionDigits = str.length - dot - 1;
        return node;
      },
      stringify: stringifyNumber.stringifyNumber
    };
    exports.float = float;
    exports.floatExp = floatExp;
    exports.floatNaN = floatNaN;
  }
});

// node_modules/yaml/dist/schema/core/int.js
var require_int = __commonJS({
  "node_modules/yaml/dist/schema/core/int.js"(exports) {
    "use strict";
    var stringifyNumber = require_stringifyNumber();
    var intIdentify = (value) => typeof value === "bigint" || Number.isInteger(value);
    var intResolve = (str, offset, radix, { intAsBigInt }) => intAsBigInt ? BigInt(str) : parseInt(str.substring(offset), radix);
    function intStringify(node, radix, prefix) {
      const { value } = node;
      if (intIdentify(value) && value >= 0)
        return prefix + value.toString(radix);
      return stringifyNumber.stringifyNumber(node);
    }
    var intOct = {
      identify: (value) => intIdentify(value) && value >= 0,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "OCT",
      test: /^0o[0-7]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 8, opt),
      stringify: (node) => intStringify(node, 8, "0o")
    };
    var int = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      test: /^[-+]?[0-9]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 0, 10, opt),
      stringify: stringifyNumber.stringifyNumber
    };
    var intHex = {
      identify: (value) => intIdentify(value) && value >= 0,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "HEX",
      test: /^0x[0-9a-fA-F]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 16, opt),
      stringify: (node) => intStringify(node, 16, "0x")
    };
    exports.int = int;
    exports.intHex = intHex;
    exports.intOct = intOct;
  }
});

// node_modules/yaml/dist/schema/core/schema.js
var require_schema = __commonJS({
  "node_modules/yaml/dist/schema/core/schema.js"(exports) {
    "use strict";
    var map = require_map();
    var _null = require_null();
    var seq = require_seq();
    var string = require_string();
    var bool = require_bool();
    var float = require_float();
    var int = require_int();
    var schema = [
      map.map,
      seq.seq,
      string.string,
      _null.nullTag,
      bool.boolTag,
      int.intOct,
      int.int,
      int.intHex,
      float.floatNaN,
      float.floatExp,
      float.float
    ];
    exports.schema = schema;
  }
});

// node_modules/yaml/dist/schema/json/schema.js
var require_schema2 = __commonJS({
  "node_modules/yaml/dist/schema/json/schema.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var map = require_map();
    var seq = require_seq();
    function intIdentify(value) {
      return typeof value === "bigint" || Number.isInteger(value);
    }
    var stringifyJSON = ({ value }) => JSON.stringify(value);
    var jsonScalars = [
      {
        identify: (value) => typeof value === "string",
        default: true,
        tag: "tag:yaml.org,2002:str",
        resolve: (str) => str,
        stringify: stringifyJSON
      },
      {
        identify: (value) => value == null,
        createNode: () => new Scalar.Scalar(null),
        default: true,
        tag: "tag:yaml.org,2002:null",
        test: /^null$/,
        resolve: () => null,
        stringify: stringifyJSON
      },
      {
        identify: (value) => typeof value === "boolean",
        default: true,
        tag: "tag:yaml.org,2002:bool",
        test: /^true$|^false$/,
        resolve: (str) => str === "true",
        stringify: stringifyJSON
      },
      {
        identify: intIdentify,
        default: true,
        tag: "tag:yaml.org,2002:int",
        test: /^-?(?:0|[1-9][0-9]*)$/,
        resolve: (str, _onError, { intAsBigInt }) => intAsBigInt ? BigInt(str) : parseInt(str, 10),
        stringify: ({ value }) => intIdentify(value) ? value.toString() : JSON.stringify(value)
      },
      {
        identify: (value) => typeof value === "number",
        default: true,
        tag: "tag:yaml.org,2002:float",
        test: /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?$/,
        resolve: (str) => parseFloat(str),
        stringify: stringifyJSON
      }
    ];
    var jsonError = {
      default: true,
      tag: "",
      test: /^/,
      resolve(str, onError) {
        onError(`Unresolved plain scalar ${JSON.stringify(str)}`);
        return str;
      }
    };
    var schema = [map.map, seq.seq].concat(jsonScalars, jsonError);
    exports.schema = schema;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/binary.js
var require_binary = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/binary.js"(exports) {
    "use strict";
    var node_buffer = __require("buffer");
    var Scalar = require_Scalar();
    var stringifyString = require_stringifyString();
    var binary = {
      identify: (value) => value instanceof Uint8Array,
      // Buffer inherits from Uint8Array
      default: false,
      tag: "tag:yaml.org,2002:binary",
      /**
       * Returns a Buffer in node and an Uint8Array in browsers
       *
       * To use the resulting buffer as an image, you'll want to do something like:
       *
       *   const blob = new Blob([buffer], { type: 'image/jpeg' })
       *   document.querySelector('#photo').src = URL.createObjectURL(blob)
       */
      resolve(src, onError) {
        if (typeof node_buffer.Buffer === "function") {
          return node_buffer.Buffer.from(src, "base64");
        } else if (typeof atob === "function") {
          const str = atob(src.replace(/[\n\r]/g, ""));
          const buffer = new Uint8Array(str.length);
          for (let i = 0; i < str.length; ++i)
            buffer[i] = str.charCodeAt(i);
          return buffer;
        } else {
          onError("This environment does not support reading binary tags; either Buffer or atob is required");
          return src;
        }
      },
      stringify({ comment, type, value }, ctx, onComment, onChompKeep) {
        if (!value)
          return "";
        const buf = value;
        let str;
        if (typeof node_buffer.Buffer === "function") {
          str = buf instanceof node_buffer.Buffer ? buf.toString("base64") : node_buffer.Buffer.from(buf.buffer).toString("base64");
        } else if (typeof btoa === "function") {
          let s = "";
          for (let i = 0; i < buf.length; ++i)
            s += String.fromCharCode(buf[i]);
          str = btoa(s);
        } else {
          throw new Error("This environment does not support writing binary tags; either Buffer or btoa is required");
        }
        type ?? (type = Scalar.Scalar.BLOCK_LITERAL);
        if (type !== Scalar.Scalar.QUOTE_DOUBLE) {
          const lineWidth = Math.max(ctx.options.lineWidth - ctx.indent.length, ctx.options.minContentWidth);
          const n = Math.ceil(str.length / lineWidth);
          const lines = new Array(n);
          for (let i = 0, o = 0; i < n; ++i, o += lineWidth) {
            lines[i] = str.substr(o, lineWidth);
          }
          str = lines.join(type === Scalar.Scalar.BLOCK_LITERAL ? "\n" : " ");
        }
        return stringifyString.stringifyString({ comment, type, value: str }, ctx, onComment, onChompKeep);
      }
    };
    exports.binary = binary;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/pairs.js
var require_pairs = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/pairs.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Pair = require_Pair();
    var Scalar = require_Scalar();
    var YAMLSeq = require_YAMLSeq();
    function resolvePairs(seq, onError) {
      if (identity.isSeq(seq)) {
        for (let i = 0; i < seq.items.length; ++i) {
          let item = seq.items[i];
          if (identity.isPair(item))
            continue;
          else if (identity.isMap(item)) {
            if (item.items.length > 1)
              onError("Each pair must have its own sequence indicator");
            const pair = item.items[0] || new Pair.Pair(new Scalar.Scalar(null));
            if (item.commentBefore)
              pair.key.commentBefore = pair.key.commentBefore ? `${item.commentBefore}
${pair.key.commentBefore}` : item.commentBefore;
            if (item.comment) {
              const cn = pair.value ?? pair.key;
              cn.comment = cn.comment ? `${item.comment}
${cn.comment}` : item.comment;
            }
            item = pair;
          }
          seq.items[i] = identity.isPair(item) ? item : new Pair.Pair(item);
        }
      } else
        onError("Expected a sequence for this tag");
      return seq;
    }
    function createPairs(schema, iterable, ctx) {
      const { replacer } = ctx;
      const pairs2 = new YAMLSeq.YAMLSeq(schema);
      pairs2.tag = "tag:yaml.org,2002:pairs";
      let i = 0;
      if (iterable && Symbol.iterator in Object(iterable))
        for (let it of iterable) {
          if (typeof replacer === "function")
            it = replacer.call(iterable, String(i++), it);
          let key, value;
          if (Array.isArray(it)) {
            if (it.length === 2) {
              key = it[0];
              value = it[1];
            } else
              throw new TypeError(`Expected [key, value] tuple: ${it}`);
          } else if (it && it instanceof Object) {
            const keys = Object.keys(it);
            if (keys.length === 1) {
              key = keys[0];
              value = it[key];
            } else {
              throw new TypeError(`Expected tuple with one key, not ${keys.length} keys`);
            }
          } else {
            key = it;
          }
          pairs2.items.push(Pair.createPair(key, value, ctx));
        }
      return pairs2;
    }
    var pairs = {
      collection: "seq",
      default: false,
      tag: "tag:yaml.org,2002:pairs",
      resolve: resolvePairs,
      createNode: createPairs
    };
    exports.createPairs = createPairs;
    exports.pairs = pairs;
    exports.resolvePairs = resolvePairs;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/omap.js
var require_omap = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/omap.js"(exports) {
    "use strict";
    var identity = require_identity();
    var toJS = require_toJS();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var pairs = require_pairs();
    var YAMLOMap = class _YAMLOMap extends YAMLSeq.YAMLSeq {
      constructor() {
        super();
        this.add = YAMLMap.YAMLMap.prototype.add.bind(this);
        this.delete = YAMLMap.YAMLMap.prototype.delete.bind(this);
        this.get = YAMLMap.YAMLMap.prototype.get.bind(this);
        this.has = YAMLMap.YAMLMap.prototype.has.bind(this);
        this.set = YAMLMap.YAMLMap.prototype.set.bind(this);
        this.tag = _YAMLOMap.tag;
      }
      /**
       * If `ctx` is given, the return type is actually `Map<unknown, unknown>`,
       * but TypeScript won't allow widening the signature of a child method.
       */
      toJSON(_, ctx) {
        if (!ctx)
          return super.toJSON(_);
        const map = /* @__PURE__ */ new Map();
        if (ctx?.onCreate)
          ctx.onCreate(map);
        for (const pair of this.items) {
          let key, value;
          if (identity.isPair(pair)) {
            key = toJS.toJS(pair.key, "", ctx);
            value = toJS.toJS(pair.value, key, ctx);
          } else {
            key = toJS.toJS(pair, "", ctx);
          }
          if (map.has(key))
            throw new Error("Ordered maps must not include duplicate keys");
          map.set(key, value);
        }
        return map;
      }
      static from(schema, iterable, ctx) {
        const pairs$1 = pairs.createPairs(schema, iterable, ctx);
        const omap2 = new this();
        omap2.items = pairs$1.items;
        return omap2;
      }
    };
    YAMLOMap.tag = "tag:yaml.org,2002:omap";
    var omap = {
      collection: "seq",
      identify: (value) => value instanceof Map,
      nodeClass: YAMLOMap,
      default: false,
      tag: "tag:yaml.org,2002:omap",
      resolve(seq, onError) {
        const pairs$1 = pairs.resolvePairs(seq, onError);
        const seenKeys = [];
        for (const { key } of pairs$1.items) {
          if (identity.isScalar(key)) {
            if (seenKeys.includes(key.value)) {
              onError(`Ordered maps must not include duplicate keys: ${key.value}`);
            } else {
              seenKeys.push(key.value);
            }
          }
        }
        return Object.assign(new YAMLOMap(), pairs$1);
      },
      createNode: (schema, iterable, ctx) => YAMLOMap.from(schema, iterable, ctx)
    };
    exports.YAMLOMap = YAMLOMap;
    exports.omap = omap;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/bool.js
var require_bool2 = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/bool.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    function boolStringify({ value, source }, ctx) {
      const boolObj = value ? trueTag : falseTag;
      if (source && boolObj.test.test(source))
        return source;
      return value ? ctx.options.trueStr : ctx.options.falseStr;
    }
    var trueTag = {
      identify: (value) => value === true,
      default: true,
      tag: "tag:yaml.org,2002:bool",
      test: /^(?:Y|y|[Yy]es|YES|[Tt]rue|TRUE|[Oo]n|ON)$/,
      resolve: () => new Scalar.Scalar(true),
      stringify: boolStringify
    };
    var falseTag = {
      identify: (value) => value === false,
      default: true,
      tag: "tag:yaml.org,2002:bool",
      test: /^(?:N|n|[Nn]o|NO|[Ff]alse|FALSE|[Oo]ff|OFF)$/,
      resolve: () => new Scalar.Scalar(false),
      stringify: boolStringify
    };
    exports.falseTag = falseTag;
    exports.trueTag = trueTag;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/float.js
var require_float2 = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/float.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var stringifyNumber = require_stringifyNumber();
    var floatNaN = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^(?:[-+]?\.(?:inf|Inf|INF)|\.nan|\.NaN|\.NAN)$/,
      resolve: (str) => str.slice(-3).toLowerCase() === "nan" ? NaN : str[0] === "-" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY,
      stringify: stringifyNumber.stringifyNumber
    };
    var floatExp = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      format: "EXP",
      test: /^[-+]?(?:[0-9][0-9_]*)?(?:\.[0-9_]*)?[eE][-+]?[0-9]+$/,
      resolve: (str) => parseFloat(str.replace(/_/g, "")),
      stringify(node) {
        const num = Number(node.value);
        return isFinite(num) ? num.toExponential() : stringifyNumber.stringifyNumber(node);
      }
    };
    var float = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^[-+]?(?:[0-9][0-9_]*)?\.[0-9_]*$/,
      resolve(str) {
        const node = new Scalar.Scalar(parseFloat(str.replace(/_/g, "")));
        const dot = str.indexOf(".");
        if (dot !== -1) {
          const f = str.substring(dot + 1).replace(/_/g, "");
          if (f[f.length - 1] === "0")
            node.minFractionDigits = f.length;
        }
        return node;
      },
      stringify: stringifyNumber.stringifyNumber
    };
    exports.float = float;
    exports.floatExp = floatExp;
    exports.floatNaN = floatNaN;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/int.js
var require_int2 = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/int.js"(exports) {
    "use strict";
    var stringifyNumber = require_stringifyNumber();
    var intIdentify = (value) => typeof value === "bigint" || Number.isInteger(value);
    function intResolve(str, offset, radix, { intAsBigInt }) {
      const sign = str[0];
      if (sign === "-" || sign === "+")
        offset += 1;
      str = str.substring(offset).replace(/_/g, "");
      if (intAsBigInt) {
        switch (radix) {
          case 2:
            str = `0b${str}`;
            break;
          case 8:
            str = `0o${str}`;
            break;
          case 16:
            str = `0x${str}`;
            break;
        }
        const n2 = BigInt(str);
        return sign === "-" ? BigInt(-1) * n2 : n2;
      }
      const n = parseInt(str, radix);
      return sign === "-" ? -1 * n : n;
    }
    function intStringify(node, radix, prefix) {
      const { value } = node;
      if (intIdentify(value)) {
        const str = value.toString(radix);
        return value < 0 ? "-" + prefix + str.substr(1) : prefix + str;
      }
      return stringifyNumber.stringifyNumber(node);
    }
    var intBin = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "BIN",
      test: /^[-+]?0b[0-1_]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 2, opt),
      stringify: (node) => intStringify(node, 2, "0b")
    };
    var intOct = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "OCT",
      test: /^[-+]?0[0-7_]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 1, 8, opt),
      stringify: (node) => intStringify(node, 8, "0")
    };
    var int = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      test: /^[-+]?[0-9][0-9_]*$/,
      resolve: (str, _onError, opt) => intResolve(str, 0, 10, opt),
      stringify: stringifyNumber.stringifyNumber
    };
    var intHex = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "HEX",
      test: /^[-+]?0x[0-9a-fA-F_]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 16, opt),
      stringify: (node) => intStringify(node, 16, "0x")
    };
    exports.int = int;
    exports.intBin = intBin;
    exports.intHex = intHex;
    exports.intOct = intOct;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/set.js
var require_set = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/set.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Pair = require_Pair();
    var YAMLMap = require_YAMLMap();
    var YAMLSet = class _YAMLSet extends YAMLMap.YAMLMap {
      constructor(schema) {
        super(schema);
        this.tag = _YAMLSet.tag;
      }
      add(key) {
        let pair;
        if (identity.isPair(key))
          pair = key;
        else if (key && typeof key === "object" && "key" in key && "value" in key && key.value === null)
          pair = new Pair.Pair(key.key, null);
        else
          pair = new Pair.Pair(key, null);
        const prev = YAMLMap.findPair(this.items, pair.key);
        if (!prev)
          this.items.push(pair);
      }
      /**
       * If `keepPair` is `true`, returns the Pair matching `key`.
       * Otherwise, returns the value of that Pair's key.
       */
      get(key, keepPair) {
        const pair = YAMLMap.findPair(this.items, key);
        return !keepPair && identity.isPair(pair) ? identity.isScalar(pair.key) ? pair.key.value : pair.key : pair;
      }
      set(key, value) {
        if (typeof value !== "boolean")
          throw new Error(`Expected boolean value for set(key, value) in a YAML set, not ${typeof value}`);
        const prev = YAMLMap.findPair(this.items, key);
        if (prev && !value) {
          this.items.splice(this.items.indexOf(prev), 1);
        } else if (!prev && value) {
          this.items.push(new Pair.Pair(key));
        }
      }
      toJSON(_, ctx) {
        return super.toJSON(_, ctx, Set);
      }
      toString(ctx, onComment, onChompKeep) {
        if (!ctx)
          return JSON.stringify(this);
        if (this.hasAllNullValues(true))
          return super.toString(Object.assign({}, ctx, { allNullValues: true }), onComment, onChompKeep);
        else
          throw new Error("Set items must all have null values");
      }
      static from(schema, iterable, ctx) {
        const { replacer } = ctx;
        const set2 = new this(schema);
        if (iterable && Symbol.iterator in Object(iterable))
          for (let value of iterable) {
            if (typeof replacer === "function")
              value = replacer.call(iterable, value, value);
            set2.items.push(Pair.createPair(value, null, ctx));
          }
        return set2;
      }
    };
    YAMLSet.tag = "tag:yaml.org,2002:set";
    var set = {
      collection: "map",
      identify: (value) => value instanceof Set,
      nodeClass: YAMLSet,
      default: false,
      tag: "tag:yaml.org,2002:set",
      createNode: (schema, iterable, ctx) => YAMLSet.from(schema, iterable, ctx),
      resolve(map, onError) {
        if (identity.isMap(map)) {
          if (map.hasAllNullValues(true))
            return Object.assign(new YAMLSet(), map);
          else
            onError("Set items must all have null values");
        } else
          onError("Expected a mapping for this tag");
        return map;
      }
    };
    exports.YAMLSet = YAMLSet;
    exports.set = set;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/timestamp.js
var require_timestamp = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/timestamp.js"(exports) {
    "use strict";
    var stringifyNumber = require_stringifyNumber();
    function parseSexagesimal(str, asBigInt) {
      const sign = str[0];
      const parts = sign === "-" || sign === "+" ? str.substring(1) : str;
      const num = (n) => asBigInt ? BigInt(n) : Number(n);
      const res = parts.replace(/_/g, "").split(":").reduce((res2, p) => res2 * num(60) + num(p), num(0));
      return sign === "-" ? num(-1) * res : res;
    }
    function stringifySexagesimal(node) {
      let { value } = node;
      let num = (n) => n;
      if (typeof value === "bigint")
        num = (n) => BigInt(n);
      else if (isNaN(value) || !isFinite(value))
        return stringifyNumber.stringifyNumber(node);
      let sign = "";
      if (value < 0) {
        sign = "-";
        value *= num(-1);
      }
      const _60 = num(60);
      const parts = [value % _60];
      if (value < 60) {
        parts.unshift(0);
      } else {
        value = (value - parts[0]) / _60;
        parts.unshift(value % _60);
        if (value >= 60) {
          value = (value - parts[0]) / _60;
          parts.unshift(value);
        }
      }
      return sign + parts.map((n) => String(n).padStart(2, "0")).join(":").replace(/000000\d*$/, "");
    }
    var intTime = {
      identify: (value) => typeof value === "bigint" || Number.isInteger(value),
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "TIME",
      test: /^[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+$/,
      resolve: (str, _onError, { intAsBigInt }) => parseSexagesimal(str, intAsBigInt),
      stringify: stringifySexagesimal
    };
    var floatTime = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      format: "TIME",
      test: /^[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*$/,
      resolve: (str) => parseSexagesimal(str, false),
      stringify: stringifySexagesimal
    };
    var timestamp = {
      identify: (value) => value instanceof Date,
      default: true,
      tag: "tag:yaml.org,2002:timestamp",
      // If the time zone is omitted, the timestamp is assumed to be specified in UTC. The time part
      // may be omitted altogether, resulting in a date format. In such a case, the time part is
      // assumed to be 00:00:00Z (start of day, UTC).
      test: RegExp("^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:(?:t|T|[ \\t]+)([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2}(\\.[0-9]+)?)(?:[ \\t]*(Z|[-+][012]?[0-9](?::[0-9]{2})?))?)?$"),
      resolve(str) {
        const match2 = str.match(timestamp.test);
        if (!match2)
          throw new Error("!!timestamp expects a date, starting with yyyy-mm-dd");
        const [, year, month, day, hour, minute, second] = match2.map(Number);
        const millisec = match2[7] ? Number((match2[7] + "00").substr(1, 3)) : 0;
        let date = Date.UTC(year, month - 1, day, hour || 0, minute || 0, second || 0, millisec);
        const tz = match2[8];
        if (tz && tz !== "Z") {
          let d = parseSexagesimal(tz, false);
          if (Math.abs(d) < 30)
            d *= 60;
          date -= 6e4 * d;
        }
        return new Date(date);
      },
      stringify: ({ value }) => value?.toISOString().replace(/(T00:00:00)?\.000Z$/, "") ?? ""
    };
    exports.floatTime = floatTime;
    exports.intTime = intTime;
    exports.timestamp = timestamp;
  }
});

// node_modules/yaml/dist/schema/yaml-1.1/schema.js
var require_schema3 = __commonJS({
  "node_modules/yaml/dist/schema/yaml-1.1/schema.js"(exports) {
    "use strict";
    var map = require_map();
    var _null = require_null();
    var seq = require_seq();
    var string = require_string();
    var binary = require_binary();
    var bool = require_bool2();
    var float = require_float2();
    var int = require_int2();
    var merge = require_merge();
    var omap = require_omap();
    var pairs = require_pairs();
    var set = require_set();
    var timestamp = require_timestamp();
    var schema = [
      map.map,
      seq.seq,
      string.string,
      _null.nullTag,
      bool.trueTag,
      bool.falseTag,
      int.intBin,
      int.intOct,
      int.int,
      int.intHex,
      float.floatNaN,
      float.floatExp,
      float.float,
      binary.binary,
      merge.merge,
      omap.omap,
      pairs.pairs,
      set.set,
      timestamp.intTime,
      timestamp.floatTime,
      timestamp.timestamp
    ];
    exports.schema = schema;
  }
});

// node_modules/yaml/dist/schema/tags.js
var require_tags = __commonJS({
  "node_modules/yaml/dist/schema/tags.js"(exports) {
    "use strict";
    var map = require_map();
    var _null = require_null();
    var seq = require_seq();
    var string = require_string();
    var bool = require_bool();
    var float = require_float();
    var int = require_int();
    var schema = require_schema();
    var schema$1 = require_schema2();
    var binary = require_binary();
    var merge = require_merge();
    var omap = require_omap();
    var pairs = require_pairs();
    var schema$2 = require_schema3();
    var set = require_set();
    var timestamp = require_timestamp();
    var schemas = /* @__PURE__ */ new Map([
      ["core", schema.schema],
      ["failsafe", [map.map, seq.seq, string.string]],
      ["json", schema$1.schema],
      ["yaml11", schema$2.schema],
      ["yaml-1.1", schema$2.schema]
    ]);
    var tagsByName = {
      binary: binary.binary,
      bool: bool.boolTag,
      float: float.float,
      floatExp: float.floatExp,
      floatNaN: float.floatNaN,
      floatTime: timestamp.floatTime,
      int: int.int,
      intHex: int.intHex,
      intOct: int.intOct,
      intTime: timestamp.intTime,
      map: map.map,
      merge: merge.merge,
      null: _null.nullTag,
      omap: omap.omap,
      pairs: pairs.pairs,
      seq: seq.seq,
      set: set.set,
      timestamp: timestamp.timestamp
    };
    var coreKnownTags = {
      "tag:yaml.org,2002:binary": binary.binary,
      "tag:yaml.org,2002:merge": merge.merge,
      "tag:yaml.org,2002:omap": omap.omap,
      "tag:yaml.org,2002:pairs": pairs.pairs,
      "tag:yaml.org,2002:set": set.set,
      "tag:yaml.org,2002:timestamp": timestamp.timestamp
    };
    function getTags(customTags, schemaName, addMergeTag) {
      const schemaTags = schemas.get(schemaName);
      if (schemaTags && !customTags) {
        return addMergeTag && !schemaTags.includes(merge.merge) ? schemaTags.concat(merge.merge) : schemaTags.slice();
      }
      let tags = schemaTags;
      if (!tags) {
        if (Array.isArray(customTags))
          tags = [];
        else {
          const keys = Array.from(schemas.keys()).filter((key) => key !== "yaml11").map((key) => JSON.stringify(key)).join(", ");
          throw new Error(`Unknown schema "${schemaName}"; use one of ${keys} or define customTags array`);
        }
      }
      if (Array.isArray(customTags)) {
        for (const tag of customTags)
          tags = tags.concat(tag);
      } else if (typeof customTags === "function") {
        tags = customTags(tags.slice());
      }
      if (addMergeTag)
        tags = tags.concat(merge.merge);
      return tags.reduce((tags2, tag) => {
        const tagObj = typeof tag === "string" ? tagsByName[tag] : tag;
        if (!tagObj) {
          const tagName = JSON.stringify(tag);
          const keys = Object.keys(tagsByName).map((key) => JSON.stringify(key)).join(", ");
          throw new Error(`Unknown custom tag ${tagName}; use one of ${keys}`);
        }
        if (!tags2.includes(tagObj))
          tags2.push(tagObj);
        return tags2;
      }, []);
    }
    exports.coreKnownTags = coreKnownTags;
    exports.getTags = getTags;
  }
});

// node_modules/yaml/dist/schema/Schema.js
var require_Schema = __commonJS({
  "node_modules/yaml/dist/schema/Schema.js"(exports) {
    "use strict";
    var identity = require_identity();
    var map = require_map();
    var seq = require_seq();
    var string = require_string();
    var tags = require_tags();
    var sortMapEntriesByKey = (a, b) => a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
    var Schema = class _Schema {
      constructor({ compat, customTags, merge, resolveKnownTags, schema, sortMapEntries, toStringDefaults }) {
        this.compat = Array.isArray(compat) ? tags.getTags(compat, "compat") : compat ? tags.getTags(null, compat) : null;
        this.name = typeof schema === "string" && schema || "core";
        this.knownTags = resolveKnownTags ? tags.coreKnownTags : {};
        this.tags = tags.getTags(customTags, this.name, merge);
        this.toStringOptions = toStringDefaults ?? null;
        Object.defineProperty(this, identity.MAP, { value: map.map });
        Object.defineProperty(this, identity.SCALAR, { value: string.string });
        Object.defineProperty(this, identity.SEQ, { value: seq.seq });
        this.sortMapEntries = typeof sortMapEntries === "function" ? sortMapEntries : sortMapEntries === true ? sortMapEntriesByKey : null;
      }
      clone() {
        const copy = Object.create(_Schema.prototype, Object.getOwnPropertyDescriptors(this));
        copy.tags = this.tags.slice();
        return copy;
      }
    };
    exports.Schema = Schema;
  }
});

// node_modules/yaml/dist/stringify/stringifyDocument.js
var require_stringifyDocument = __commonJS({
  "node_modules/yaml/dist/stringify/stringifyDocument.js"(exports) {
    "use strict";
    var identity = require_identity();
    var stringify = require_stringify();
    var stringifyComment = require_stringifyComment();
    function stringifyDocument(doc, options) {
      const lines = [];
      let hasDirectives = options.directives === true;
      if (options.directives !== false && doc.directives) {
        const dir = doc.directives.toString(doc);
        if (dir) {
          lines.push(dir);
          hasDirectives = true;
        } else if (doc.directives.docStart)
          hasDirectives = true;
      }
      if (hasDirectives)
        lines.push("---");
      const ctx = stringify.createStringifyContext(doc, options);
      const { commentString } = ctx.options;
      if (doc.commentBefore) {
        if (lines.length !== 1)
          lines.unshift("");
        const cs = commentString(doc.commentBefore);
        lines.unshift(stringifyComment.indentComment(cs, ""));
      }
      let chompKeep = false;
      let contentComment = null;
      if (doc.contents) {
        if (identity.isNode(doc.contents)) {
          if (doc.contents.spaceBefore && hasDirectives)
            lines.push("");
          if (doc.contents.commentBefore) {
            const cs = commentString(doc.contents.commentBefore);
            lines.push(stringifyComment.indentComment(cs, ""));
          }
          ctx.forceBlockIndent = !!doc.comment;
          contentComment = doc.contents.comment;
        }
        const onChompKeep = contentComment ? void 0 : () => chompKeep = true;
        let body = stringify.stringify(doc.contents, ctx, () => contentComment = null, onChompKeep);
        if (contentComment)
          body += stringifyComment.lineComment(body, "", commentString(contentComment));
        if ((body[0] === "|" || body[0] === ">") && lines[lines.length - 1] === "---") {
          lines[lines.length - 1] = `--- ${body}`;
        } else
          lines.push(body);
      } else {
        lines.push(stringify.stringify(doc.contents, ctx));
      }
      if (doc.directives?.docEnd) {
        if (doc.comment) {
          const cs = commentString(doc.comment);
          if (cs.includes("\n")) {
            lines.push("...");
            lines.push(stringifyComment.indentComment(cs, ""));
          } else {
            lines.push(`... ${cs}`);
          }
        } else {
          lines.push("...");
        }
      } else {
        let dc = doc.comment;
        if (dc && chompKeep)
          dc = dc.replace(/^\n+/, "");
        if (dc) {
          if ((!chompKeep || contentComment) && lines[lines.length - 1] !== "")
            lines.push("");
          lines.push(stringifyComment.indentComment(commentString(dc), ""));
        }
      }
      return lines.join("\n") + "\n";
    }
    exports.stringifyDocument = stringifyDocument;
  }
});

// node_modules/yaml/dist/doc/Document.js
var require_Document = __commonJS({
  "node_modules/yaml/dist/doc/Document.js"(exports) {
    "use strict";
    var Alias = require_Alias();
    var Collection = require_Collection();
    var identity = require_identity();
    var Pair = require_Pair();
    var toJS = require_toJS();
    var Schema = require_Schema();
    var stringifyDocument = require_stringifyDocument();
    var anchors = require_anchors();
    var applyReviver = require_applyReviver();
    var createNode = require_createNode();
    var directives = require_directives();
    var Document = class _Document {
      constructor(value, replacer, options) {
        this.commentBefore = null;
        this.comment = null;
        this.errors = [];
        this.warnings = [];
        Object.defineProperty(this, identity.NODE_TYPE, { value: identity.DOC });
        let _replacer = null;
        if (typeof replacer === "function" || Array.isArray(replacer)) {
          _replacer = replacer;
        } else if (options === void 0 && replacer) {
          options = replacer;
          replacer = void 0;
        }
        const opt = Object.assign({
          intAsBigInt: false,
          keepSourceTokens: false,
          logLevel: "warn",
          prettyErrors: true,
          strict: true,
          stringKeys: false,
          uniqueKeys: true,
          version: "1.2"
        }, options);
        this.options = opt;
        let { version } = opt;
        if (options?._directives) {
          this.directives = options._directives.atDocument();
          if (this.directives.yaml.explicit)
            version = this.directives.yaml.version;
        } else
          this.directives = new directives.Directives({ version });
        this.setSchema(version, options);
        this.contents = value === void 0 ? null : this.createNode(value, _replacer, options);
      }
      /**
       * Create a deep copy of this Document and its contents.
       *
       * Custom Node values that inherit from `Object` still refer to their original instances.
       */
      clone() {
        const copy = Object.create(_Document.prototype, {
          [identity.NODE_TYPE]: { value: identity.DOC }
        });
        copy.commentBefore = this.commentBefore;
        copy.comment = this.comment;
        copy.errors = this.errors.slice();
        copy.warnings = this.warnings.slice();
        copy.options = Object.assign({}, this.options);
        if (this.directives)
          copy.directives = this.directives.clone();
        copy.schema = this.schema.clone();
        copy.contents = identity.isNode(this.contents) ? this.contents.clone(copy.schema) : this.contents;
        if (this.range)
          copy.range = this.range.slice();
        return copy;
      }
      /** Adds a value to the document. */
      add(value) {
        if (assertCollection(this.contents))
          this.contents.add(value);
      }
      /** Adds a value to the document. */
      addIn(path34, value) {
        if (assertCollection(this.contents))
          this.contents.addIn(path34, value);
      }
      /**
       * Create a new `Alias` node, ensuring that the target `node` has the required anchor.
       *
       * If `node` already has an anchor, `name` is ignored.
       * Otherwise, the `node.anchor` value will be set to `name`,
       * or if an anchor with that name is already present in the document,
       * `name` will be used as a prefix for a new unique anchor.
       * If `name` is undefined, the generated anchor will use 'a' as a prefix.
       */
      createAlias(node, name) {
        if (!node.anchor) {
          const prev = anchors.anchorNames(this);
          node.anchor = // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing
          !name || prev.has(name) ? anchors.findNewAnchor(name || "a", prev) : name;
        }
        return new Alias.Alias(node.anchor);
      }
      createNode(value, replacer, options) {
        let _replacer = void 0;
        if (typeof replacer === "function") {
          value = replacer.call({ "": value }, "", value);
          _replacer = replacer;
        } else if (Array.isArray(replacer)) {
          const keyToStr = (v) => typeof v === "number" || v instanceof String || v instanceof Number;
          const asStr = replacer.filter(keyToStr).map(String);
          if (asStr.length > 0)
            replacer = replacer.concat(asStr);
          _replacer = replacer;
        } else if (options === void 0 && replacer) {
          options = replacer;
          replacer = void 0;
        }
        const { aliasDuplicateObjects, anchorPrefix, flow, keepUndefined, onTagObj, tag } = options ?? {};
        const { onAnchor, setAnchors, sourceObjects } = anchors.createNodeAnchors(
          this,
          // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing
          anchorPrefix || "a"
        );
        const ctx = {
          aliasDuplicateObjects: aliasDuplicateObjects ?? true,
          keepUndefined: keepUndefined ?? false,
          onAnchor,
          onTagObj,
          replacer: _replacer,
          schema: this.schema,
          sourceObjects
        };
        const node = createNode.createNode(value, tag, ctx);
        if (flow && identity.isCollection(node))
          node.flow = true;
        setAnchors();
        return node;
      }
      /**
       * Convert a key and a value into a `Pair` using the current schema,
       * recursively wrapping all values as `Scalar` or `Collection` nodes.
       */
      createPair(key, value, options = {}) {
        const k = this.createNode(key, null, options);
        const v = this.createNode(value, null, options);
        return new Pair.Pair(k, v);
      }
      /**
       * Removes a value from the document.
       * @returns `true` if the item was found and removed.
       */
      delete(key) {
        return assertCollection(this.contents) ? this.contents.delete(key) : false;
      }
      /**
       * Removes a value from the document.
       * @returns `true` if the item was found and removed.
       */
      deleteIn(path34) {
        if (Collection.isEmptyPath(path34)) {
          if (this.contents == null)
            return false;
          this.contents = null;
          return true;
        }
        return assertCollection(this.contents) ? this.contents.deleteIn(path34) : false;
      }
      /**
       * Returns item at `key`, or `undefined` if not found. By default unwraps
       * scalar values from their surrounding node; to disable set `keepScalar` to
       * `true` (collections are always returned intact).
       */
      get(key, keepScalar) {
        return identity.isCollection(this.contents) ? this.contents.get(key, keepScalar) : void 0;
      }
      /**
       * Returns item at `path`, or `undefined` if not found. By default unwraps
       * scalar values from their surrounding node; to disable set `keepScalar` to
       * `true` (collections are always returned intact).
       */
      getIn(path34, keepScalar) {
        if (Collection.isEmptyPath(path34))
          return !keepScalar && identity.isScalar(this.contents) ? this.contents.value : this.contents;
        return identity.isCollection(this.contents) ? this.contents.getIn(path34, keepScalar) : void 0;
      }
      /**
       * Checks if the document includes a value with the key `key`.
       */
      has(key) {
        return identity.isCollection(this.contents) ? this.contents.has(key) : false;
      }
      /**
       * Checks if the document includes a value at `path`.
       */
      hasIn(path34) {
        if (Collection.isEmptyPath(path34))
          return this.contents !== void 0;
        return identity.isCollection(this.contents) ? this.contents.hasIn(path34) : false;
      }
      /**
       * Sets a value in this document. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       */
      set(key, value) {
        if (this.contents == null) {
          this.contents = Collection.collectionFromPath(this.schema, [key], value);
        } else if (assertCollection(this.contents)) {
          this.contents.set(key, value);
        }
      }
      /**
       * Sets a value in this document. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       */
      setIn(path34, value) {
        if (Collection.isEmptyPath(path34)) {
          this.contents = value;
        } else if (this.contents == null) {
          this.contents = Collection.collectionFromPath(this.schema, Array.from(path34), value);
        } else if (assertCollection(this.contents)) {
          this.contents.setIn(path34, value);
        }
      }
      /**
       * Change the YAML version and schema used by the document.
       * A `null` version disables support for directives, explicit tags, anchors, and aliases.
       * It also requires the `schema` option to be given as a `Schema` instance value.
       *
       * Overrides all previously set schema options.
       */
      setSchema(version, options = {}) {
        if (typeof version === "number")
          version = String(version);
        let opt;
        switch (version) {
          case "1.1":
            if (this.directives)
              this.directives.yaml.version = "1.1";
            else
              this.directives = new directives.Directives({ version: "1.1" });
            opt = { resolveKnownTags: false, schema: "yaml-1.1" };
            break;
          case "1.2":
          case "next":
            if (this.directives)
              this.directives.yaml.version = version;
            else
              this.directives = new directives.Directives({ version });
            opt = { resolveKnownTags: true, schema: "core" };
            break;
          case null:
            if (this.directives)
              delete this.directives;
            opt = null;
            break;
          default: {
            const sv = JSON.stringify(version);
            throw new Error(`Expected '1.1', '1.2' or null as first argument, but found: ${sv}`);
          }
        }
        if (options.schema instanceof Object)
          this.schema = options.schema;
        else if (opt)
          this.schema = new Schema.Schema(Object.assign(opt, options));
        else
          throw new Error(`With a null YAML version, the { schema: Schema } option is required`);
      }
      // json & jsonArg are only used from toJSON()
      toJS({ json, jsonArg, mapAsMap, maxAliasCount, onAnchor, reviver } = {}) {
        const ctx = {
          anchors: /* @__PURE__ */ new Map(),
          doc: this,
          keep: !json,
          mapAsMap: mapAsMap === true,
          mapKeyWarned: false,
          maxAliasCount: typeof maxAliasCount === "number" ? maxAliasCount : 100
        };
        const res = toJS.toJS(this.contents, jsonArg ?? "", ctx);
        if (typeof onAnchor === "function")
          for (const { count: count2, res: res2 } of ctx.anchors.values())
            onAnchor(res2, count2);
        return typeof reviver === "function" ? applyReviver.applyReviver(reviver, { "": res }, "", res) : res;
      }
      /**
       * A JSON representation of the document `contents`.
       *
       * @param jsonArg Used by `JSON.stringify` to indicate the array index or
       *   property name.
       */
      toJSON(jsonArg, onAnchor) {
        return this.toJS({ json: true, jsonArg, mapAsMap: false, onAnchor });
      }
      /** A YAML representation of the document. */
      toString(options = {}) {
        if (this.errors.length > 0)
          throw new Error("Document with errors cannot be stringified");
        if ("indent" in options && (!Number.isInteger(options.indent) || Number(options.indent) <= 0)) {
          const s = JSON.stringify(options.indent);
          throw new Error(`"indent" option must be a positive integer, not ${s}`);
        }
        return stringifyDocument.stringifyDocument(this, options);
      }
    };
    function assertCollection(contents) {
      if (identity.isCollection(contents))
        return true;
      throw new Error("Expected a YAML collection as document contents");
    }
    exports.Document = Document;
  }
});

// node_modules/yaml/dist/errors.js
var require_errors = __commonJS({
  "node_modules/yaml/dist/errors.js"(exports) {
    "use strict";
    var YAMLError = class extends Error {
      constructor(name, pos, code, message) {
        super();
        this.name = name;
        this.code = code;
        this.message = message;
        this.pos = pos;
      }
    };
    var YAMLParseError = class extends YAMLError {
      constructor(pos, code, message) {
        super("YAMLParseError", pos, code, message);
      }
    };
    var YAMLWarning = class extends YAMLError {
      constructor(pos, code, message) {
        super("YAMLWarning", pos, code, message);
      }
    };
    var prettifyError = (src, lc) => (error) => {
      if (error.pos[0] === -1)
        return;
      error.linePos = error.pos.map((pos) => lc.linePos(pos));
      const { line, col } = error.linePos[0];
      error.message += ` at line ${line}, column ${col}`;
      let ci = col - 1;
      let lineStr = src.substring(lc.lineStarts[line - 1], lc.lineStarts[line]).replace(/[\n\r]+$/, "");
      if (ci >= 60 && lineStr.length > 80) {
        const trimStart = Math.min(ci - 39, lineStr.length - 79);
        lineStr = "\u2026" + lineStr.substring(trimStart);
        ci -= trimStart - 1;
      }
      if (lineStr.length > 80)
        lineStr = lineStr.substring(0, 79) + "\u2026";
      if (line > 1 && /^ *$/.test(lineStr.substring(0, ci))) {
        let prev = src.substring(lc.lineStarts[line - 2], lc.lineStarts[line - 1]);
        if (prev.length > 80)
          prev = prev.substring(0, 79) + "\u2026\n";
        lineStr = prev + lineStr;
      }
      if (/[^ ]/.test(lineStr)) {
        let count2 = 1;
        const end = error.linePos[1];
        if (end?.line === line && end.col > col) {
          count2 = Math.max(1, Math.min(end.col - col, 80 - ci));
        }
        const pointer = " ".repeat(ci) + "^".repeat(count2);
        error.message += `:

${lineStr}
${pointer}
`;
      }
    };
    exports.YAMLError = YAMLError;
    exports.YAMLParseError = YAMLParseError;
    exports.YAMLWarning = YAMLWarning;
    exports.prettifyError = prettifyError;
  }
});

// node_modules/yaml/dist/compose/resolve-props.js
var require_resolve_props = __commonJS({
  "node_modules/yaml/dist/compose/resolve-props.js"(exports) {
    "use strict";
    function resolveProps(tokens, { flow, indicator, next, offset, onError, parentIndent, startOnNewline }) {
      let spaceBefore = false;
      let atNewline = startOnNewline;
      let hasSpace = startOnNewline;
      let comment = "";
      let commentSep = "";
      let hasNewline = false;
      let reqSpace = false;
      let tab = null;
      let anchor = null;
      let tag = null;
      let newlineAfterProp = null;
      let comma = null;
      let found = null;
      let start = null;
      for (const token of tokens) {
        if (reqSpace) {
          if (token.type !== "space" && token.type !== "newline" && token.type !== "comma")
            onError(token.offset, "MISSING_CHAR", "Tags and anchors must be separated from the next token by white space");
          reqSpace = false;
        }
        if (tab) {
          if (atNewline && token.type !== "comment" && token.type !== "newline") {
            onError(tab, "TAB_AS_INDENT", "Tabs are not allowed as indentation");
          }
          tab = null;
        }
        switch (token.type) {
          case "space":
            if (!flow && (indicator !== "doc-start" || next?.type !== "flow-collection") && token.source.includes("	")) {
              tab = token;
            }
            hasSpace = true;
            break;
          case "comment": {
            if (!hasSpace)
              onError(token, "MISSING_CHAR", "Comments must be separated from other tokens by white space characters");
            const cb = token.source.substring(1) || " ";
            if (!comment)
              comment = cb;
            else
              comment += commentSep + cb;
            commentSep = "";
            atNewline = false;
            break;
          }
          case "newline":
            if (atNewline) {
              if (comment)
                comment += token.source;
              else if (!found || indicator !== "seq-item-ind")
                spaceBefore = true;
            } else
              commentSep += token.source;
            atNewline = true;
            hasNewline = true;
            if (anchor || tag)
              newlineAfterProp = token;
            hasSpace = true;
            break;
          case "anchor":
            if (anchor)
              onError(token, "MULTIPLE_ANCHORS", "A node can have at most one anchor");
            if (token.source.endsWith(":"))
              onError(token.offset + token.source.length - 1, "BAD_ALIAS", "Anchor ending in : is ambiguous", true);
            anchor = token;
            start ?? (start = token.offset);
            atNewline = false;
            hasSpace = false;
            reqSpace = true;
            break;
          case "tag": {
            if (tag)
              onError(token, "MULTIPLE_TAGS", "A node can have at most one tag");
            tag = token;
            start ?? (start = token.offset);
            atNewline = false;
            hasSpace = false;
            reqSpace = true;
            break;
          }
          case indicator:
            if (anchor || tag)
              onError(token, "BAD_PROP_ORDER", `Anchors and tags must be after the ${token.source} indicator`);
            if (found)
              onError(token, "UNEXPECTED_TOKEN", `Unexpected ${token.source} in ${flow ?? "collection"}`);
            found = token;
            atNewline = indicator === "seq-item-ind" || indicator === "explicit-key-ind";
            hasSpace = false;
            break;
          case "comma":
            if (flow) {
              if (comma)
                onError(token, "UNEXPECTED_TOKEN", `Unexpected , in ${flow}`);
              comma = token;
              atNewline = false;
              hasSpace = false;
              break;
            }
          // else fallthrough
          default:
            onError(token, "UNEXPECTED_TOKEN", `Unexpected ${token.type} token`);
            atNewline = false;
            hasSpace = false;
        }
      }
      const last = tokens[tokens.length - 1];
      const end = last ? last.offset + last.source.length : offset;
      if (reqSpace && next && next.type !== "space" && next.type !== "newline" && next.type !== "comma" && (next.type !== "scalar" || next.source !== "")) {
        onError(next.offset, "MISSING_CHAR", "Tags and anchors must be separated from the next token by white space");
      }
      if (tab && (atNewline && tab.indent <= parentIndent || next?.type === "block-map" || next?.type === "block-seq"))
        onError(tab, "TAB_AS_INDENT", "Tabs are not allowed as indentation");
      return {
        comma,
        found,
        spaceBefore,
        comment,
        hasNewline,
        anchor,
        tag,
        newlineAfterProp,
        end,
        start: start ?? end
      };
    }
    exports.resolveProps = resolveProps;
  }
});

// node_modules/yaml/dist/compose/util-contains-newline.js
var require_util_contains_newline = __commonJS({
  "node_modules/yaml/dist/compose/util-contains-newline.js"(exports) {
    "use strict";
    function containsNewline(key) {
      if (!key)
        return null;
      switch (key.type) {
        case "alias":
        case "scalar":
        case "double-quoted-scalar":
        case "single-quoted-scalar":
          if (key.source.includes("\n"))
            return true;
          if (key.end) {
            for (const st of key.end)
              if (st.type === "newline")
                return true;
          }
          return false;
        case "flow-collection":
          for (const it of key.items) {
            for (const st of it.start)
              if (st.type === "newline")
                return true;
            if (it.sep) {
              for (const st of it.sep)
                if (st.type === "newline")
                  return true;
            }
            if (containsNewline(it.key) || containsNewline(it.value))
              return true;
          }
          return false;
        default:
          return true;
      }
    }
    exports.containsNewline = containsNewline;
  }
});

// node_modules/yaml/dist/compose/util-flow-indent-check.js
var require_util_flow_indent_check = __commonJS({
  "node_modules/yaml/dist/compose/util-flow-indent-check.js"(exports) {
    "use strict";
    var utilContainsNewline = require_util_contains_newline();
    function flowIndentCheck(indent, fc, onError) {
      if (fc?.type === "flow-collection") {
        const end = fc.end[0];
        if (end.indent === indent && (end.source === "]" || end.source === "}") && utilContainsNewline.containsNewline(fc)) {
          const msg = "Flow end indicator should be more indented than parent";
          onError(end, "BAD_INDENT", msg, true);
        }
      }
    }
    exports.flowIndentCheck = flowIndentCheck;
  }
});

// node_modules/yaml/dist/compose/util-map-includes.js
var require_util_map_includes = __commonJS({
  "node_modules/yaml/dist/compose/util-map-includes.js"(exports) {
    "use strict";
    var identity = require_identity();
    function mapIncludes(ctx, items, search) {
      const { uniqueKeys } = ctx.options;
      if (uniqueKeys === false)
        return false;
      const isEqual = typeof uniqueKeys === "function" ? uniqueKeys : (a, b) => a === b || identity.isScalar(a) && identity.isScalar(b) && a.value === b.value;
      return items.some((pair) => isEqual(pair.key, search));
    }
    exports.mapIncludes = mapIncludes;
  }
});

// node_modules/yaml/dist/compose/resolve-block-map.js
var require_resolve_block_map = __commonJS({
  "node_modules/yaml/dist/compose/resolve-block-map.js"(exports) {
    "use strict";
    var Pair = require_Pair();
    var YAMLMap = require_YAMLMap();
    var resolveProps = require_resolve_props();
    var utilContainsNewline = require_util_contains_newline();
    var utilFlowIndentCheck = require_util_flow_indent_check();
    var utilMapIncludes = require_util_map_includes();
    var startColMsg = "All mapping items must start at the same column";
    function resolveBlockMap({ composeNode, composeEmptyNode }, ctx, bm, onError, tag) {
      const NodeClass = tag?.nodeClass ?? YAMLMap.YAMLMap;
      const map = new NodeClass(ctx.schema);
      if (ctx.atRoot)
        ctx.atRoot = false;
      let offset = bm.offset;
      let commentEnd = null;
      for (const collItem of bm.items) {
        const { start, key, sep: sep10, value } = collItem;
        const keyProps = resolveProps.resolveProps(start, {
          indicator: "explicit-key-ind",
          next: key ?? sep10?.[0],
          offset,
          onError,
          parentIndent: bm.indent,
          startOnNewline: true
        });
        const implicitKey = !keyProps.found;
        if (implicitKey) {
          if (key) {
            if (key.type === "block-seq")
              onError(offset, "BLOCK_AS_IMPLICIT_KEY", "A block sequence may not be used as an implicit map key");
            else if ("indent" in key && key.indent !== bm.indent)
              onError(offset, "BAD_INDENT", startColMsg);
          }
          if (!keyProps.anchor && !keyProps.tag && !sep10) {
            commentEnd = keyProps.end;
            if (keyProps.comment) {
              if (map.comment)
                map.comment += "\n" + keyProps.comment;
              else
                map.comment = keyProps.comment;
            }
            continue;
          }
          if (keyProps.newlineAfterProp || utilContainsNewline.containsNewline(key)) {
            onError(key ?? start[start.length - 1], "MULTILINE_IMPLICIT_KEY", "Implicit keys need to be on a single line");
          }
        } else if (keyProps.found?.indent !== bm.indent) {
          onError(offset, "BAD_INDENT", startColMsg);
        }
        ctx.atKey = true;
        const keyStart = keyProps.end;
        const keyNode = key ? composeNode(ctx, key, keyProps, onError) : composeEmptyNode(ctx, keyStart, start, null, keyProps, onError);
        if (ctx.schema.compat)
          utilFlowIndentCheck.flowIndentCheck(bm.indent, key, onError);
        ctx.atKey = false;
        if (utilMapIncludes.mapIncludes(ctx, map.items, keyNode))
          onError(keyStart, "DUPLICATE_KEY", "Map keys must be unique");
        const valueProps = resolveProps.resolveProps(sep10 ?? [], {
          indicator: "map-value-ind",
          next: value,
          offset: keyNode.range[2],
          onError,
          parentIndent: bm.indent,
          startOnNewline: !key || key.type === "block-scalar"
        });
        offset = valueProps.end;
        if (valueProps.found) {
          if (implicitKey) {
            if (value?.type === "block-map" && !valueProps.hasNewline)
              onError(offset, "BLOCK_AS_IMPLICIT_KEY", "Nested mappings are not allowed in compact mappings");
            if (ctx.options.strict && keyProps.start < valueProps.found.offset - 1024)
              onError(keyNode.range, "KEY_OVER_1024_CHARS", "The : indicator must be at most 1024 chars after the start of an implicit block mapping key");
          }
          const valueNode = value ? composeNode(ctx, value, valueProps, onError) : composeEmptyNode(ctx, offset, sep10, null, valueProps, onError);
          if (ctx.schema.compat)
            utilFlowIndentCheck.flowIndentCheck(bm.indent, value, onError);
          offset = valueNode.range[2];
          const pair = new Pair.Pair(keyNode, valueNode);
          if (ctx.options.keepSourceTokens)
            pair.srcToken = collItem;
          map.items.push(pair);
        } else {
          if (implicitKey)
            onError(keyNode.range, "MISSING_CHAR", "Implicit map keys need to be followed by map values");
          if (valueProps.comment) {
            if (keyNode.comment)
              keyNode.comment += "\n" + valueProps.comment;
            else
              keyNode.comment = valueProps.comment;
          }
          const pair = new Pair.Pair(keyNode);
          if (ctx.options.keepSourceTokens)
            pair.srcToken = collItem;
          map.items.push(pair);
        }
      }
      if (commentEnd && commentEnd < offset)
        onError(commentEnd, "IMPOSSIBLE", "Map comment with trailing content");
      map.range = [bm.offset, offset, commentEnd ?? offset];
      return map;
    }
    exports.resolveBlockMap = resolveBlockMap;
  }
});

// node_modules/yaml/dist/compose/resolve-block-seq.js
var require_resolve_block_seq = __commonJS({
  "node_modules/yaml/dist/compose/resolve-block-seq.js"(exports) {
    "use strict";
    var YAMLSeq = require_YAMLSeq();
    var resolveProps = require_resolve_props();
    var utilFlowIndentCheck = require_util_flow_indent_check();
    function resolveBlockSeq({ composeNode, composeEmptyNode }, ctx, bs, onError, tag) {
      const NodeClass = tag?.nodeClass ?? YAMLSeq.YAMLSeq;
      const seq = new NodeClass(ctx.schema);
      if (ctx.atRoot)
        ctx.atRoot = false;
      if (ctx.atKey)
        ctx.atKey = false;
      let offset = bs.offset;
      let commentEnd = null;
      for (const { start, value } of bs.items) {
        const props = resolveProps.resolveProps(start, {
          indicator: "seq-item-ind",
          next: value,
          offset,
          onError,
          parentIndent: bs.indent,
          startOnNewline: true
        });
        if (!props.found) {
          if (props.anchor || props.tag || value) {
            if (value?.type === "block-seq")
              onError(props.end, "BAD_INDENT", "All sequence items must start at the same column");
            else
              onError(offset, "MISSING_CHAR", "Sequence item without - indicator");
          } else {
            commentEnd = props.end;
            if (props.comment)
              seq.comment = props.comment;
            continue;
          }
        }
        const node = value ? composeNode(ctx, value, props, onError) : composeEmptyNode(ctx, props.end, start, null, props, onError);
        if (ctx.schema.compat)
          utilFlowIndentCheck.flowIndentCheck(bs.indent, value, onError);
        offset = node.range[2];
        seq.items.push(node);
      }
      seq.range = [bs.offset, offset, commentEnd ?? offset];
      return seq;
    }
    exports.resolveBlockSeq = resolveBlockSeq;
  }
});

// node_modules/yaml/dist/compose/resolve-end.js
var require_resolve_end = __commonJS({
  "node_modules/yaml/dist/compose/resolve-end.js"(exports) {
    "use strict";
    function resolveEnd(end, offset, reqSpace, onError) {
      let comment = "";
      if (end) {
        let hasSpace = false;
        let sep10 = "";
        for (const token of end) {
          const { source, type } = token;
          switch (type) {
            case "space":
              hasSpace = true;
              break;
            case "comment": {
              if (reqSpace && !hasSpace)
                onError(token, "MISSING_CHAR", "Comments must be separated from other tokens by white space characters");
              const cb = source.substring(1) || " ";
              if (!comment)
                comment = cb;
              else
                comment += sep10 + cb;
              sep10 = "";
              break;
            }
            case "newline":
              if (comment)
                sep10 += source;
              hasSpace = true;
              break;
            default:
              onError(token, "UNEXPECTED_TOKEN", `Unexpected ${type} at node end`);
          }
          offset += source.length;
        }
      }
      return { comment, offset };
    }
    exports.resolveEnd = resolveEnd;
  }
});

// node_modules/yaml/dist/compose/resolve-flow-collection.js
var require_resolve_flow_collection = __commonJS({
  "node_modules/yaml/dist/compose/resolve-flow-collection.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Pair = require_Pair();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var resolveEnd = require_resolve_end();
    var resolveProps = require_resolve_props();
    var utilContainsNewline = require_util_contains_newline();
    var utilMapIncludes = require_util_map_includes();
    var blockMsg = "Block collections are not allowed within flow collections";
    var isBlock = (token) => token && (token.type === "block-map" || token.type === "block-seq");
    function resolveFlowCollection({ composeNode, composeEmptyNode }, ctx, fc, onError, tag) {
      const isMap2 = fc.start.source === "{";
      const fcName = isMap2 ? "flow map" : "flow sequence";
      const NodeClass = tag?.nodeClass ?? (isMap2 ? YAMLMap.YAMLMap : YAMLSeq.YAMLSeq);
      const coll = new NodeClass(ctx.schema);
      coll.flow = true;
      const atRoot = ctx.atRoot;
      if (atRoot)
        ctx.atRoot = false;
      if (ctx.atKey)
        ctx.atKey = false;
      let offset = fc.offset + fc.start.source.length;
      for (let i = 0; i < fc.items.length; ++i) {
        const collItem = fc.items[i];
        const { start, key, sep: sep10, value } = collItem;
        const props = resolveProps.resolveProps(start, {
          flow: fcName,
          indicator: "explicit-key-ind",
          next: key ?? sep10?.[0],
          offset,
          onError,
          parentIndent: fc.indent,
          startOnNewline: false
        });
        if (!props.found) {
          if (!props.anchor && !props.tag && !sep10 && !value) {
            if (i === 0 && props.comma)
              onError(props.comma, "UNEXPECTED_TOKEN", `Unexpected , in ${fcName}`);
            else if (i < fc.items.length - 1)
              onError(props.start, "UNEXPECTED_TOKEN", `Unexpected empty item in ${fcName}`);
            if (props.comment) {
              if (coll.comment)
                coll.comment += "\n" + props.comment;
              else
                coll.comment = props.comment;
            }
            offset = props.end;
            continue;
          }
          if (!isMap2 && ctx.options.strict && utilContainsNewline.containsNewline(key))
            onError(
              key,
              // checked by containsNewline()
              "MULTILINE_IMPLICIT_KEY",
              "Implicit keys of flow sequence pairs need to be on a single line"
            );
        }
        if (i === 0) {
          if (props.comma)
            onError(props.comma, "UNEXPECTED_TOKEN", `Unexpected , in ${fcName}`);
        } else {
          if (!props.comma)
            onError(props.start, "MISSING_CHAR", `Missing , between ${fcName} items`);
          if (props.comment) {
            let prevItemComment = "";
            loop: for (const st of start) {
              switch (st.type) {
                case "comma":
                case "space":
                  break;
                case "comment":
                  prevItemComment = st.source.substring(1);
                  break loop;
                default:
                  break loop;
              }
            }
            if (prevItemComment) {
              let prev = coll.items[coll.items.length - 1];
              if (identity.isPair(prev))
                prev = prev.value ?? prev.key;
              if (prev.comment)
                prev.comment += "\n" + prevItemComment;
              else
                prev.comment = prevItemComment;
              props.comment = props.comment.substring(prevItemComment.length + 1);
            }
          }
        }
        if (!isMap2 && !sep10 && !props.found) {
          const valueNode = value ? composeNode(ctx, value, props, onError) : composeEmptyNode(ctx, props.end, sep10, null, props, onError);
          coll.items.push(valueNode);
          offset = valueNode.range[2];
          if (isBlock(value))
            onError(valueNode.range, "BLOCK_IN_FLOW", blockMsg);
        } else {
          ctx.atKey = true;
          const keyStart = props.end;
          const keyNode = key ? composeNode(ctx, key, props, onError) : composeEmptyNode(ctx, keyStart, start, null, props, onError);
          if (isBlock(key))
            onError(keyNode.range, "BLOCK_IN_FLOW", blockMsg);
          ctx.atKey = false;
          const valueProps = resolveProps.resolveProps(sep10 ?? [], {
            flow: fcName,
            indicator: "map-value-ind",
            next: value,
            offset: keyNode.range[2],
            onError,
            parentIndent: fc.indent,
            startOnNewline: false
          });
          if (valueProps.found) {
            if (!isMap2 && !props.found && ctx.options.strict) {
              if (sep10)
                for (const st of sep10) {
                  if (st === valueProps.found)
                    break;
                  if (st.type === "newline") {
                    onError(st, "MULTILINE_IMPLICIT_KEY", "Implicit keys of flow sequence pairs need to be on a single line");
                    break;
                  }
                }
              if (props.start < valueProps.found.offset - 1024)
                onError(valueProps.found, "KEY_OVER_1024_CHARS", "The : indicator must be at most 1024 chars after the start of an implicit flow sequence key");
            }
          } else if (value) {
            if ("source" in value && value.source?.[0] === ":")
              onError(value, "MISSING_CHAR", `Missing space after : in ${fcName}`);
            else
              onError(valueProps.start, "MISSING_CHAR", `Missing , or : between ${fcName} items`);
          }
          const valueNode = value ? composeNode(ctx, value, valueProps, onError) : valueProps.found ? composeEmptyNode(ctx, valueProps.end, sep10, null, valueProps, onError) : null;
          if (valueNode) {
            if (isBlock(value))
              onError(valueNode.range, "BLOCK_IN_FLOW", blockMsg);
          } else if (valueProps.comment) {
            if (keyNode.comment)
              keyNode.comment += "\n" + valueProps.comment;
            else
              keyNode.comment = valueProps.comment;
          }
          const pair = new Pair.Pair(keyNode, valueNode);
          if (ctx.options.keepSourceTokens)
            pair.srcToken = collItem;
          if (isMap2) {
            const map = coll;
            if (utilMapIncludes.mapIncludes(ctx, map.items, keyNode))
              onError(keyStart, "DUPLICATE_KEY", "Map keys must be unique");
            map.items.push(pair);
          } else {
            const map = new YAMLMap.YAMLMap(ctx.schema);
            map.flow = true;
            map.items.push(pair);
            const endRange = (valueNode ?? keyNode).range;
            map.range = [keyNode.range[0], endRange[1], endRange[2]];
            coll.items.push(map);
          }
          offset = valueNode ? valueNode.range[2] : valueProps.end;
        }
      }
      const expectedEnd = isMap2 ? "}" : "]";
      const [ce, ...ee] = fc.end;
      let cePos = offset;
      if (ce?.source === expectedEnd)
        cePos = ce.offset + ce.source.length;
      else {
        const name = fcName[0].toUpperCase() + fcName.substring(1);
        const msg = atRoot ? `${name} must end with a ${expectedEnd}` : `${name} in block collection must be sufficiently indented and end with a ${expectedEnd}`;
        onError(offset, atRoot ? "MISSING_CHAR" : "BAD_INDENT", msg);
        if (ce && ce.source.length !== 1)
          ee.unshift(ce);
      }
      if (ee.length > 0) {
        const end = resolveEnd.resolveEnd(ee, cePos, ctx.options.strict, onError);
        if (end.comment) {
          if (coll.comment)
            coll.comment += "\n" + end.comment;
          else
            coll.comment = end.comment;
        }
        coll.range = [fc.offset, cePos, end.offset];
      } else {
        coll.range = [fc.offset, cePos, cePos];
      }
      return coll;
    }
    exports.resolveFlowCollection = resolveFlowCollection;
  }
});

// node_modules/yaml/dist/compose/compose-collection.js
var require_compose_collection = __commonJS({
  "node_modules/yaml/dist/compose/compose-collection.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var resolveBlockMap = require_resolve_block_map();
    var resolveBlockSeq = require_resolve_block_seq();
    var resolveFlowCollection = require_resolve_flow_collection();
    function resolveCollection(CN, ctx, token, onError, tagName, tag) {
      const coll = token.type === "block-map" ? resolveBlockMap.resolveBlockMap(CN, ctx, token, onError, tag) : token.type === "block-seq" ? resolveBlockSeq.resolveBlockSeq(CN, ctx, token, onError, tag) : resolveFlowCollection.resolveFlowCollection(CN, ctx, token, onError, tag);
      const Coll = coll.constructor;
      if (tagName === "!" || tagName === Coll.tagName) {
        coll.tag = Coll.tagName;
        return coll;
      }
      if (tagName)
        coll.tag = tagName;
      return coll;
    }
    function composeCollection(CN, ctx, token, props, onError) {
      const tagToken = props.tag;
      const tagName = !tagToken ? null : ctx.directives.tagName(tagToken.source, (msg) => onError(tagToken, "TAG_RESOLVE_FAILED", msg));
      if (token.type === "block-seq") {
        const { anchor, newlineAfterProp: nl } = props;
        const lastProp = anchor && tagToken ? anchor.offset > tagToken.offset ? anchor : tagToken : anchor ?? tagToken;
        if (lastProp && (!nl || nl.offset < lastProp.offset)) {
          const message = "Missing newline after block sequence props";
          onError(lastProp, "MISSING_CHAR", message);
        }
      }
      const expType = token.type === "block-map" ? "map" : token.type === "block-seq" ? "seq" : token.start.source === "{" ? "map" : "seq";
      if (!tagToken || !tagName || tagName === "!" || tagName === YAMLMap.YAMLMap.tagName && expType === "map" || tagName === YAMLSeq.YAMLSeq.tagName && expType === "seq") {
        return resolveCollection(CN, ctx, token, onError, tagName);
      }
      let tag = ctx.schema.tags.find((t) => t.tag === tagName && t.collection === expType);
      if (!tag) {
        const kt = ctx.schema.knownTags[tagName];
        if (kt?.collection === expType) {
          ctx.schema.tags.push(Object.assign({}, kt, { default: false }));
          tag = kt;
        } else {
          if (kt) {
            onError(tagToken, "BAD_COLLECTION_TYPE", `${kt.tag} used for ${expType} collection, but expects ${kt.collection ?? "scalar"}`, true);
          } else {
            onError(tagToken, "TAG_RESOLVE_FAILED", `Unresolved tag: ${tagName}`, true);
          }
          return resolveCollection(CN, ctx, token, onError, tagName);
        }
      }
      const coll = resolveCollection(CN, ctx, token, onError, tagName, tag);
      const res = tag.resolve?.(coll, (msg) => onError(tagToken, "TAG_RESOLVE_FAILED", msg), ctx.options) ?? coll;
      const node = identity.isNode(res) ? res : new Scalar.Scalar(res);
      node.range = coll.range;
      node.tag = tagName;
      if (tag?.format)
        node.format = tag.format;
      return node;
    }
    exports.composeCollection = composeCollection;
  }
});

// node_modules/yaml/dist/compose/resolve-block-scalar.js
var require_resolve_block_scalar = __commonJS({
  "node_modules/yaml/dist/compose/resolve-block-scalar.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    function resolveBlockScalar(ctx, scalar, onError) {
      const start = scalar.offset;
      const header = parseBlockScalarHeader(scalar, ctx.options.strict, onError);
      if (!header)
        return { value: "", type: null, comment: "", range: [start, start, start] };
      const type = header.mode === ">" ? Scalar.Scalar.BLOCK_FOLDED : Scalar.Scalar.BLOCK_LITERAL;
      const lines = scalar.source ? splitLines(scalar.source) : [];
      let chompStart = lines.length;
      for (let i = lines.length - 1; i >= 0; --i) {
        const content = lines[i][1];
        if (content === "" || content === "\r")
          chompStart = i;
        else
          break;
      }
      if (chompStart === 0) {
        const value2 = header.chomp === "+" && lines.length > 0 ? "\n".repeat(Math.max(1, lines.length - 1)) : "";
        let end2 = start + header.length;
        if (scalar.source)
          end2 += scalar.source.length;
        return { value: value2, type, comment: header.comment, range: [start, end2, end2] };
      }
      let trimIndent = scalar.indent + header.indent;
      let offset = scalar.offset + header.length;
      let contentStart = 0;
      for (let i = 0; i < chompStart; ++i) {
        const [indent, content] = lines[i];
        if (content === "" || content === "\r") {
          if (header.indent === 0 && indent.length > trimIndent)
            trimIndent = indent.length;
        } else {
          if (indent.length < trimIndent) {
            const message = "Block scalars with more-indented leading empty lines must use an explicit indentation indicator";
            onError(offset + indent.length, "MISSING_CHAR", message);
          }
          if (header.indent === 0)
            trimIndent = indent.length;
          contentStart = i;
          if (trimIndent === 0 && !ctx.atRoot) {
            const message = "Block scalar values in collections must be indented";
            onError(offset, "BAD_INDENT", message);
          }
          break;
        }
        offset += indent.length + content.length + 1;
      }
      for (let i = lines.length - 1; i >= chompStart; --i) {
        if (lines[i][0].length > trimIndent)
          chompStart = i + 1;
      }
      let value = "";
      let sep10 = "";
      let prevMoreIndented = false;
      for (let i = 0; i < contentStart; ++i)
        value += lines[i][0].slice(trimIndent) + "\n";
      for (let i = contentStart; i < chompStart; ++i) {
        let [indent, content] = lines[i];
        offset += indent.length + content.length + 1;
        const crlf = content[content.length - 1] === "\r";
        if (crlf)
          content = content.slice(0, -1);
        if (content && indent.length < trimIndent) {
          const src = header.indent ? "explicit indentation indicator" : "first line";
          const message = `Block scalar lines must not be less indented than their ${src}`;
          onError(offset - content.length - (crlf ? 2 : 1), "BAD_INDENT", message);
          indent = "";
        }
        if (type === Scalar.Scalar.BLOCK_LITERAL) {
          value += sep10 + indent.slice(trimIndent) + content;
          sep10 = "\n";
        } else if (indent.length > trimIndent || content[0] === "	") {
          if (sep10 === " ")
            sep10 = "\n";
          else if (!prevMoreIndented && sep10 === "\n")
            sep10 = "\n\n";
          value += sep10 + indent.slice(trimIndent) + content;
          sep10 = "\n";
          prevMoreIndented = true;
        } else if (content === "") {
          if (sep10 === "\n")
            value += "\n";
          else
            sep10 = "\n";
        } else {
          value += sep10 + content;
          sep10 = " ";
          prevMoreIndented = false;
        }
      }
      switch (header.chomp) {
        case "-":
          break;
        case "+":
          for (let i = chompStart; i < lines.length; ++i)
            value += "\n" + lines[i][0].slice(trimIndent);
          if (value[value.length - 1] !== "\n")
            value += "\n";
          break;
        default:
          value += "\n";
      }
      const end = start + header.length + scalar.source.length;
      return { value, type, comment: header.comment, range: [start, end, end] };
    }
    function parseBlockScalarHeader({ offset, props }, strict, onError) {
      if (props[0].type !== "block-scalar-header") {
        onError(props[0], "IMPOSSIBLE", "Block scalar header not found");
        return null;
      }
      const { source } = props[0];
      const mode = source[0];
      let indent = 0;
      let chomp = "";
      let error = -1;
      for (let i = 1; i < source.length; ++i) {
        const ch = source[i];
        if (!chomp && (ch === "-" || ch === "+"))
          chomp = ch;
        else {
          const n = Number(ch);
          if (!indent && n)
            indent = n;
          else if (error === -1)
            error = offset + i;
        }
      }
      if (error !== -1)
        onError(error, "UNEXPECTED_TOKEN", `Block scalar header includes extra characters: ${source}`);
      let hasSpace = false;
      let comment = "";
      let length = source.length;
      for (let i = 1; i < props.length; ++i) {
        const token = props[i];
        switch (token.type) {
          case "space":
            hasSpace = true;
          // fallthrough
          case "newline":
            length += token.source.length;
            break;
          case "comment":
            if (strict && !hasSpace) {
              const message = "Comments must be separated from other tokens by white space characters";
              onError(token, "MISSING_CHAR", message);
            }
            length += token.source.length;
            comment = token.source.substring(1);
            break;
          case "error":
            onError(token, "UNEXPECTED_TOKEN", token.message);
            length += token.source.length;
            break;
          /* istanbul ignore next should not happen */
          default: {
            const message = `Unexpected token in block scalar header: ${token.type}`;
            onError(token, "UNEXPECTED_TOKEN", message);
            const ts = token.source;
            if (ts && typeof ts === "string")
              length += ts.length;
          }
        }
      }
      return { mode, indent, chomp, comment, length };
    }
    function splitLines(source) {
      const split = source.split(/\n( *)/);
      const first = split[0];
      const m = first.match(/^( *)/);
      const line0 = m?.[1] ? [m[1], first.slice(m[1].length)] : ["", first];
      const lines = [line0];
      for (let i = 1; i < split.length; i += 2)
        lines.push([split[i], split[i + 1]]);
      return lines;
    }
    exports.resolveBlockScalar = resolveBlockScalar;
  }
});

// node_modules/yaml/dist/compose/resolve-flow-scalar.js
var require_resolve_flow_scalar = __commonJS({
  "node_modules/yaml/dist/compose/resolve-flow-scalar.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var resolveEnd = require_resolve_end();
    function resolveFlowScalar(scalar, strict, onError) {
      const { offset, type, source, end } = scalar;
      let _type;
      let value;
      const _onError = (rel, code, msg) => onError(offset + rel, code, msg);
      switch (type) {
        case "scalar":
          _type = Scalar.Scalar.PLAIN;
          value = plainValue(source, _onError);
          break;
        case "single-quoted-scalar":
          _type = Scalar.Scalar.QUOTE_SINGLE;
          value = singleQuotedValue(source, _onError);
          break;
        case "double-quoted-scalar":
          _type = Scalar.Scalar.QUOTE_DOUBLE;
          value = doubleQuotedValue(source, _onError);
          break;
        /* istanbul ignore next should not happen */
        default:
          onError(scalar, "UNEXPECTED_TOKEN", `Expected a flow scalar value, but found: ${type}`);
          return {
            value: "",
            type: null,
            comment: "",
            range: [offset, offset + source.length, offset + source.length]
          };
      }
      const valueEnd = offset + source.length;
      const re = resolveEnd.resolveEnd(end, valueEnd, strict, onError);
      return {
        value,
        type: _type,
        comment: re.comment,
        range: [offset, valueEnd, re.offset]
      };
    }
    function plainValue(source, onError) {
      let badChar = "";
      switch (source[0]) {
        /* istanbul ignore next should not happen */
        case "	":
          badChar = "a tab character";
          break;
        case ",":
          badChar = "flow indicator character ,";
          break;
        case "%":
          badChar = "directive indicator character %";
          break;
        case "|":
        case ">": {
          badChar = `block scalar indicator ${source[0]}`;
          break;
        }
        case "@":
        case "`": {
          badChar = `reserved character ${source[0]}`;
          break;
        }
      }
      if (badChar)
        onError(0, "BAD_SCALAR_START", `Plain value cannot start with ${badChar}`);
      return foldLines(source);
    }
    function singleQuotedValue(source, onError) {
      if (source[source.length - 1] !== "'" || source.length === 1)
        onError(source.length, "MISSING_CHAR", "Missing closing 'quote");
      return foldLines(source.slice(1, -1)).replace(/''/g, "'");
    }
    function foldLines(source) {
      let first, line;
      try {
        first = new RegExp("(.*?)(?<![ 	])[ 	]*\r?\n", "sy");
        line = new RegExp("[ 	]*(.*?)(?:(?<![ 	])[ 	]*)?\r?\n", "sy");
      } catch {
        first = /(.*?)[ \t]*\r?\n/sy;
        line = /[ \t]*(.*?)[ \t]*\r?\n/sy;
      }
      let match2 = first.exec(source);
      if (!match2)
        return source;
      let res = match2[1];
      let sep10 = " ";
      let pos = first.lastIndex;
      line.lastIndex = pos;
      while (match2 = line.exec(source)) {
        if (match2[1] === "") {
          if (sep10 === "\n")
            res += sep10;
          else
            sep10 = "\n";
        } else {
          res += sep10 + match2[1];
          sep10 = " ";
        }
        pos = line.lastIndex;
      }
      const last = /[ \t]*(.*)/sy;
      last.lastIndex = pos;
      match2 = last.exec(source);
      return res + sep10 + (match2?.[1] ?? "");
    }
    function doubleQuotedValue(source, onError) {
      let res = "";
      for (let i = 1; i < source.length - 1; ++i) {
        const ch = source[i];
        if (ch === "\r" && source[i + 1] === "\n")
          continue;
        if (ch === "\n") {
          const { fold: fold3, offset } = foldNewline(source, i);
          res += fold3;
          i = offset;
        } else if (ch === "\\") {
          let next = source[++i];
          const cc = escapeCodes[next];
          if (cc)
            res += cc;
          else if (next === "\n") {
            next = source[i + 1];
            while (next === " " || next === "	")
              next = source[++i + 1];
          } else if (next === "\r" && source[i + 1] === "\n") {
            next = source[++i + 1];
            while (next === " " || next === "	")
              next = source[++i + 1];
          } else if (next === "x" || next === "u" || next === "U") {
            const length = next === "x" ? 2 : next === "u" ? 4 : 8;
            res += parseCharCode(source, i + 1, length, onError);
            i += length;
          } else {
            const raw = source.substr(i - 1, 2);
            onError(i - 1, "BAD_DQ_ESCAPE", `Invalid escape sequence ${raw}`);
            res += raw;
          }
        } else if (ch === " " || ch === "	") {
          const wsStart = i;
          let next = source[i + 1];
          while (next === " " || next === "	")
            next = source[++i + 1];
          if (next !== "\n" && !(next === "\r" && source[i + 2] === "\n"))
            res += i > wsStart ? source.slice(wsStart, i + 1) : ch;
        } else {
          res += ch;
        }
      }
      if (source[source.length - 1] !== '"' || source.length === 1)
        onError(source.length, "MISSING_CHAR", 'Missing closing "quote');
      return res;
    }
    function foldNewline(source, offset) {
      let fold3 = "";
      let ch = source[offset + 1];
      while (ch === " " || ch === "	" || ch === "\n" || ch === "\r") {
        if (ch === "\r" && source[offset + 2] !== "\n")
          break;
        if (ch === "\n")
          fold3 += "\n";
        offset += 1;
        ch = source[offset + 1];
      }
      if (!fold3)
        fold3 = " ";
      return { fold: fold3, offset };
    }
    var escapeCodes = {
      "0": "\0",
      // null character
      a: "\x07",
      // bell character
      b: "\b",
      // backspace
      e: "\x1B",
      // escape character
      f: "\f",
      // form feed
      n: "\n",
      // line feed
      r: "\r",
      // carriage return
      t: "	",
      // horizontal tab
      v: "\v",
      // vertical tab
      N: "\x85",
      // Unicode next line
      _: "\xA0",
      // Unicode non-breaking space
      L: "\u2028",
      // Unicode line separator
      P: "\u2029",
      // Unicode paragraph separator
      " ": " ",
      '"': '"',
      "/": "/",
      "\\": "\\",
      "	": "	"
    };
    function parseCharCode(source, offset, length, onError) {
      const cc = source.substr(offset, length);
      const ok = cc.length === length && /^[0-9a-fA-F]+$/.test(cc);
      const code = ok ? parseInt(cc, 16) : NaN;
      try {
        return String.fromCodePoint(code);
      } catch {
        const raw = source.substr(offset - 2, length + 2);
        onError(offset - 2, "BAD_DQ_ESCAPE", `Invalid escape sequence ${raw}`);
        return raw;
      }
    }
    exports.resolveFlowScalar = resolveFlowScalar;
  }
});

// node_modules/yaml/dist/compose/compose-scalar.js
var require_compose_scalar = __commonJS({
  "node_modules/yaml/dist/compose/compose-scalar.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var resolveBlockScalar = require_resolve_block_scalar();
    var resolveFlowScalar = require_resolve_flow_scalar();
    function composeScalar(ctx, token, tagToken, onError) {
      const { value, type, comment, range: range2 } = token.type === "block-scalar" ? resolveBlockScalar.resolveBlockScalar(ctx, token, onError) : resolveFlowScalar.resolveFlowScalar(token, ctx.options.strict, onError);
      const tagName = tagToken ? ctx.directives.tagName(tagToken.source, (msg) => onError(tagToken, "TAG_RESOLVE_FAILED", msg)) : null;
      let tag;
      if (ctx.options.stringKeys && ctx.atKey) {
        tag = ctx.schema[identity.SCALAR];
      } else if (tagName)
        tag = findScalarTagByName(ctx.schema, value, tagName, tagToken, onError);
      else if (token.type === "scalar")
        tag = findScalarTagByTest(ctx, value, token, onError);
      else
        tag = ctx.schema[identity.SCALAR];
      let scalar;
      try {
        const res = tag.resolve(value, (msg) => onError(tagToken ?? token, "TAG_RESOLVE_FAILED", msg), ctx.options);
        scalar = identity.isScalar(res) ? res : new Scalar.Scalar(res);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        onError(tagToken ?? token, "TAG_RESOLVE_FAILED", msg);
        scalar = new Scalar.Scalar(value);
      }
      scalar.range = range2;
      scalar.source = value;
      if (type)
        scalar.type = type;
      if (tagName)
        scalar.tag = tagName;
      if (tag.format)
        scalar.format = tag.format;
      if (comment)
        scalar.comment = comment;
      return scalar;
    }
    function findScalarTagByName(schema, value, tagName, tagToken, onError) {
      if (tagName === "!")
        return schema[identity.SCALAR];
      const matchWithTest = [];
      for (const tag of schema.tags) {
        if (!tag.collection && tag.tag === tagName) {
          if (tag.default && tag.test)
            matchWithTest.push(tag);
          else
            return tag;
        }
      }
      for (const tag of matchWithTest)
        if (tag.test?.test(value))
          return tag;
      const kt = schema.knownTags[tagName];
      if (kt && !kt.collection) {
        schema.tags.push(Object.assign({}, kt, { default: false, test: void 0 }));
        return kt;
      }
      onError(tagToken, "TAG_RESOLVE_FAILED", `Unresolved tag: ${tagName}`, tagName !== "tag:yaml.org,2002:str");
      return schema[identity.SCALAR];
    }
    function findScalarTagByTest({ atKey, directives, schema }, value, token, onError) {
      const tag = schema.tags.find((tag2) => (tag2.default === true || atKey && tag2.default === "key") && tag2.test?.test(value)) || schema[identity.SCALAR];
      if (schema.compat) {
        const compat = schema.compat.find((tag2) => tag2.default && tag2.test?.test(value)) ?? schema[identity.SCALAR];
        if (tag.tag !== compat.tag) {
          const ts = directives.tagString(tag.tag);
          const cs = directives.tagString(compat.tag);
          const msg = `Value may be parsed as either ${ts} or ${cs}`;
          onError(token, "TAG_RESOLVE_FAILED", msg, true);
        }
      }
      return tag;
    }
    exports.composeScalar = composeScalar;
  }
});

// node_modules/yaml/dist/compose/util-empty-scalar-position.js
var require_util_empty_scalar_position = __commonJS({
  "node_modules/yaml/dist/compose/util-empty-scalar-position.js"(exports) {
    "use strict";
    function emptyScalarPosition(offset, before, pos) {
      if (before) {
        pos ?? (pos = before.length);
        for (let i = pos - 1; i >= 0; --i) {
          let st = before[i];
          switch (st.type) {
            case "space":
            case "comment":
            case "newline":
              offset -= st.source.length;
              continue;
          }
          st = before[++i];
          while (st?.type === "space") {
            offset += st.source.length;
            st = before[++i];
          }
          break;
        }
      }
      return offset;
    }
    exports.emptyScalarPosition = emptyScalarPosition;
  }
});

// node_modules/yaml/dist/compose/compose-node.js
var require_compose_node = __commonJS({
  "node_modules/yaml/dist/compose/compose-node.js"(exports) {
    "use strict";
    var Alias = require_Alias();
    var identity = require_identity();
    var composeCollection = require_compose_collection();
    var composeScalar = require_compose_scalar();
    var resolveEnd = require_resolve_end();
    var utilEmptyScalarPosition = require_util_empty_scalar_position();
    var CN = { composeNode, composeEmptyNode };
    function composeNode(ctx, token, props, onError) {
      const atKey = ctx.atKey;
      const { spaceBefore, comment, anchor, tag } = props;
      let node;
      let isSrcToken = true;
      switch (token.type) {
        case "alias":
          node = composeAlias(ctx, token, onError);
          if (anchor || tag)
            onError(token, "ALIAS_PROPS", "An alias node must not specify any properties");
          break;
        case "scalar":
        case "single-quoted-scalar":
        case "double-quoted-scalar":
        case "block-scalar":
          node = composeScalar.composeScalar(ctx, token, tag, onError);
          if (anchor)
            node.anchor = anchor.source.substring(1);
          break;
        case "block-map":
        case "block-seq":
        case "flow-collection":
          try {
            node = composeCollection.composeCollection(CN, ctx, token, props, onError);
            if (anchor)
              node.anchor = anchor.source.substring(1);
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            onError(token, "RESOURCE_EXHAUSTION", message);
          }
          break;
        default: {
          const message = token.type === "error" ? token.message : `Unsupported token (type: ${token.type})`;
          onError(token, "UNEXPECTED_TOKEN", message);
          isSrcToken = false;
        }
      }
      node ?? (node = composeEmptyNode(ctx, token.offset, void 0, null, props, onError));
      if (anchor && node.anchor === "")
        onError(anchor, "BAD_ALIAS", "Anchor cannot be an empty string");
      if (atKey && ctx.options.stringKeys && (!identity.isScalar(node) || typeof node.value !== "string" || node.tag && node.tag !== "tag:yaml.org,2002:str")) {
        const msg = "With stringKeys, all keys must be strings";
        onError(tag ?? token, "NON_STRING_KEY", msg);
      }
      if (spaceBefore)
        node.spaceBefore = true;
      if (comment) {
        if (token.type === "scalar" && token.source === "")
          node.comment = comment;
        else
          node.commentBefore = comment;
      }
      if (ctx.options.keepSourceTokens && isSrcToken)
        node.srcToken = token;
      return node;
    }
    function composeEmptyNode(ctx, offset, before, pos, { spaceBefore, comment, anchor, tag, end }, onError) {
      const token = {
        type: "scalar",
        offset: utilEmptyScalarPosition.emptyScalarPosition(offset, before, pos),
        indent: -1,
        source: ""
      };
      const node = composeScalar.composeScalar(ctx, token, tag, onError);
      if (anchor) {
        node.anchor = anchor.source.substring(1);
        if (node.anchor === "")
          onError(anchor, "BAD_ALIAS", "Anchor cannot be an empty string");
      }
      if (spaceBefore)
        node.spaceBefore = true;
      if (comment) {
        node.comment = comment;
        node.range[2] = end;
      }
      return node;
    }
    function composeAlias({ options }, { offset, source, end }, onError) {
      const alias = new Alias.Alias(source.substring(1));
      if (alias.source === "")
        onError(offset, "BAD_ALIAS", "Alias cannot be an empty string");
      if (alias.source.endsWith(":"))
        onError(offset + source.length - 1, "BAD_ALIAS", "Alias ending in : is ambiguous", true);
      const valueEnd = offset + source.length;
      const re = resolveEnd.resolveEnd(end, valueEnd, options.strict, onError);
      alias.range = [offset, valueEnd, re.offset];
      if (re.comment)
        alias.comment = re.comment;
      return alias;
    }
    exports.composeEmptyNode = composeEmptyNode;
    exports.composeNode = composeNode;
  }
});

// node_modules/yaml/dist/compose/compose-doc.js
var require_compose_doc = __commonJS({
  "node_modules/yaml/dist/compose/compose-doc.js"(exports) {
    "use strict";
    var Document = require_Document();
    var composeNode = require_compose_node();
    var resolveEnd = require_resolve_end();
    var resolveProps = require_resolve_props();
    function composeDoc(options, directives, { offset, start, value, end }, onError) {
      const opts = Object.assign({ _directives: directives }, options);
      const doc = new Document.Document(void 0, opts);
      const ctx = {
        atKey: false,
        atRoot: true,
        directives: doc.directives,
        options: doc.options,
        schema: doc.schema
      };
      const props = resolveProps.resolveProps(start, {
        indicator: "doc-start",
        next: value ?? end?.[0],
        offset,
        onError,
        parentIndent: 0,
        startOnNewline: true
      });
      if (props.found) {
        doc.directives.docStart = true;
        if (value && (value.type === "block-map" || value.type === "block-seq") && !props.hasNewline)
          onError(props.end, "MISSING_CHAR", "Block collection cannot start on same line with directives-end marker");
      }
      doc.contents = value ? composeNode.composeNode(ctx, value, props, onError) : composeNode.composeEmptyNode(ctx, props.end, start, null, props, onError);
      const contentEnd = doc.contents.range[2];
      const re = resolveEnd.resolveEnd(end, contentEnd, false, onError);
      if (re.comment)
        doc.comment = re.comment;
      doc.range = [offset, contentEnd, re.offset];
      return doc;
    }
    exports.composeDoc = composeDoc;
  }
});

// node_modules/yaml/dist/compose/composer.js
var require_composer = __commonJS({
  "node_modules/yaml/dist/compose/composer.js"(exports) {
    "use strict";
    var node_process = __require("process");
    var directives = require_directives();
    var Document = require_Document();
    var errors = require_errors();
    var identity = require_identity();
    var composeDoc = require_compose_doc();
    var resolveEnd = require_resolve_end();
    function getErrorPos(src) {
      if (typeof src === "number")
        return [src, src + 1];
      if (Array.isArray(src))
        return src.length === 2 ? src : [src[0], src[1]];
      const { offset, source } = src;
      return [offset, offset + (typeof source === "string" ? source.length : 1)];
    }
    function parsePrelude(prelude) {
      let comment = "";
      let atComment = false;
      let afterEmptyLine = false;
      for (let i = 0; i < prelude.length; ++i) {
        const source = prelude[i];
        switch (source[0]) {
          case "#":
            comment += (comment === "" ? "" : afterEmptyLine ? "\n\n" : "\n") + (source.substring(1) || " ");
            atComment = true;
            afterEmptyLine = false;
            break;
          case "%":
            if (prelude[i + 1]?.[0] !== "#")
              i += 1;
            atComment = false;
            break;
          default:
            if (!atComment)
              afterEmptyLine = true;
            atComment = false;
        }
      }
      return { comment, afterEmptyLine };
    }
    var Composer = class {
      constructor(options = {}) {
        this.doc = null;
        this.atDirectives = false;
        this.prelude = [];
        this.errors = [];
        this.warnings = [];
        this.onError = (source, code, message, warning) => {
          const pos = getErrorPos(source);
          if (warning)
            this.warnings.push(new errors.YAMLWarning(pos, code, message));
          else
            this.errors.push(new errors.YAMLParseError(pos, code, message));
        };
        this.directives = new directives.Directives({ version: options.version || "1.2" });
        this.options = options;
      }
      decorate(doc, afterDoc) {
        const { comment, afterEmptyLine } = parsePrelude(this.prelude);
        if (comment) {
          const dc = doc.contents;
          if (afterDoc) {
            doc.comment = doc.comment ? `${doc.comment}
${comment}` : comment;
          } else if (afterEmptyLine || doc.directives.docStart || !dc) {
            doc.commentBefore = comment;
          } else if (identity.isCollection(dc) && !dc.flow && dc.items.length > 0) {
            let it = dc.items[0];
            if (identity.isPair(it))
              it = it.key;
            const cb = it.commentBefore;
            it.commentBefore = cb ? `${comment}
${cb}` : comment;
          } else {
            const cb = dc.commentBefore;
            dc.commentBefore = cb ? `${comment}
${cb}` : comment;
          }
        }
        if (afterDoc) {
          for (let i = 0; i < this.errors.length; ++i)
            doc.errors.push(this.errors[i]);
          for (let i = 0; i < this.warnings.length; ++i)
            doc.warnings.push(this.warnings[i]);
        } else {
          doc.errors = this.errors;
          doc.warnings = this.warnings;
        }
        this.prelude = [];
        this.errors = [];
        this.warnings = [];
      }
      /**
       * Current stream status information.
       *
       * Mostly useful at the end of input for an empty stream.
       */
      streamInfo() {
        return {
          comment: parsePrelude(this.prelude).comment,
          directives: this.directives,
          errors: this.errors,
          warnings: this.warnings
        };
      }
      /**
       * Compose tokens into documents.
       *
       * @param forceDoc - If the stream contains no document, still emit a final document including any comments and directives that would be applied to a subsequent document.
       * @param endOffset - Should be set if `forceDoc` is also set, to set the document range end and to indicate errors correctly.
       */
      *compose(tokens, forceDoc = false, endOffset = -1) {
        for (const token of tokens)
          yield* this.next(token);
        yield* this.end(forceDoc, endOffset);
      }
      /** Advance the composer by one CST token. */
      *next(token) {
        if (node_process.env.LOG_STREAM)
          console.dir(token, { depth: null });
        switch (token.type) {
          case "directive":
            this.directives.add(token.source, (offset, message, warning) => {
              const pos = getErrorPos(token);
              pos[0] += offset;
              this.onError(pos, "BAD_DIRECTIVE", message, warning);
            });
            this.prelude.push(token.source);
            this.atDirectives = true;
            break;
          case "document": {
            const doc = composeDoc.composeDoc(this.options, this.directives, token, this.onError);
            if (this.atDirectives && !doc.directives.docStart)
              this.onError(token, "MISSING_CHAR", "Missing directives-end/doc-start indicator line");
            this.decorate(doc, false);
            if (this.doc)
              yield this.doc;
            this.doc = doc;
            this.atDirectives = false;
            break;
          }
          case "byte-order-mark":
          case "space":
            break;
          case "comment":
          case "newline":
            this.prelude.push(token.source);
            break;
          case "error": {
            const msg = token.source ? `${token.message}: ${JSON.stringify(token.source)}` : token.message;
            const error = new errors.YAMLParseError(getErrorPos(token), "UNEXPECTED_TOKEN", msg);
            if (this.atDirectives || !this.doc)
              this.errors.push(error);
            else
              this.doc.errors.push(error);
            break;
          }
          case "doc-end": {
            if (!this.doc) {
              const msg = "Unexpected doc-end without preceding document";
              this.errors.push(new errors.YAMLParseError(getErrorPos(token), "UNEXPECTED_TOKEN", msg));
              break;
            }
            this.doc.directives.docEnd = true;
            const end = resolveEnd.resolveEnd(token.end, token.offset + token.source.length, this.doc.options.strict, this.onError);
            this.decorate(this.doc, true);
            if (end.comment) {
              const dc = this.doc.comment;
              this.doc.comment = dc ? `${dc}
${end.comment}` : end.comment;
            }
            this.doc.range[2] = end.offset;
            break;
          }
          default:
            this.errors.push(new errors.YAMLParseError(getErrorPos(token), "UNEXPECTED_TOKEN", `Unsupported token ${token.type}`));
        }
      }
      /**
       * Call at end of input to yield any remaining document.
       *
       * @param forceDoc - If the stream contains no document, still emit a final document including any comments and directives that would be applied to a subsequent document.
       * @param endOffset - Should be set if `forceDoc` is also set, to set the document range end and to indicate errors correctly.
       */
      *end(forceDoc = false, endOffset = -1) {
        if (this.doc) {
          this.decorate(this.doc, true);
          yield this.doc;
          this.doc = null;
        } else if (forceDoc) {
          const opts = Object.assign({ _directives: this.directives }, this.options);
          const doc = new Document.Document(void 0, opts);
          if (this.atDirectives)
            this.onError(endOffset, "MISSING_CHAR", "Missing directives-end indicator line");
          doc.range = [0, endOffset, endOffset];
          this.decorate(doc, false);
          yield doc;
        }
      }
    };
    exports.Composer = Composer;
  }
});

// node_modules/yaml/dist/parse/cst-scalar.js
var require_cst_scalar = __commonJS({
  "node_modules/yaml/dist/parse/cst-scalar.js"(exports) {
    "use strict";
    var resolveBlockScalar = require_resolve_block_scalar();
    var resolveFlowScalar = require_resolve_flow_scalar();
    var errors = require_errors();
    var stringifyString = require_stringifyString();
    function resolveAsScalar(token, strict = true, onError) {
      if (token) {
        const _onError = (pos, code, message) => {
          const offset = typeof pos === "number" ? pos : Array.isArray(pos) ? pos[0] : pos.offset;
          if (onError)
            onError(offset, code, message);
          else
            throw new errors.YAMLParseError([offset, offset + 1], code, message);
        };
        switch (token.type) {
          case "scalar":
          case "single-quoted-scalar":
          case "double-quoted-scalar":
            return resolveFlowScalar.resolveFlowScalar(token, strict, _onError);
          case "block-scalar":
            return resolveBlockScalar.resolveBlockScalar({ options: { strict } }, token, _onError);
        }
      }
      return null;
    }
    function createScalarToken(value, context) {
      const { implicitKey = false, indent, inFlow = false, offset = -1, type = "PLAIN" } = context;
      const source = stringifyString.stringifyString({ type, value }, {
        implicitKey,
        indent: indent > 0 ? " ".repeat(indent) : "",
        inFlow,
        options: { blockQuote: true, lineWidth: -1 }
      });
      const end = context.end ?? [
        { type: "newline", offset: -1, indent, source: "\n" }
      ];
      switch (source[0]) {
        case "|":
        case ">": {
          const he = source.indexOf("\n");
          const head = source.substring(0, he);
          const body = source.substring(he + 1) + "\n";
          const props = [
            { type: "block-scalar-header", offset, indent, source: head }
          ];
          if (!addEndtoBlockProps(props, end))
            props.push({ type: "newline", offset: -1, indent, source: "\n" });
          return { type: "block-scalar", offset, indent, props, source: body };
        }
        case '"':
          return { type: "double-quoted-scalar", offset, indent, source, end };
        case "'":
          return { type: "single-quoted-scalar", offset, indent, source, end };
        default:
          return { type: "scalar", offset, indent, source, end };
      }
    }
    function setScalarValue(token, value, context = {}) {
      let { afterKey = false, implicitKey = false, inFlow = false, type } = context;
      let indent = "indent" in token ? token.indent : null;
      if (afterKey && typeof indent === "number")
        indent += 2;
      if (!type)
        switch (token.type) {
          case "single-quoted-scalar":
            type = "QUOTE_SINGLE";
            break;
          case "double-quoted-scalar":
            type = "QUOTE_DOUBLE";
            break;
          case "block-scalar": {
            const header = token.props[0];
            if (header.type !== "block-scalar-header")
              throw new Error("Invalid block scalar header");
            type = header.source[0] === ">" ? "BLOCK_FOLDED" : "BLOCK_LITERAL";
            break;
          }
          default:
            type = "PLAIN";
        }
      const source = stringifyString.stringifyString({ type, value }, {
        implicitKey: implicitKey || indent === null,
        indent: indent !== null && indent > 0 ? " ".repeat(indent) : "",
        inFlow,
        options: { blockQuote: true, lineWidth: -1 }
      });
      switch (source[0]) {
        case "|":
        case ">":
          setBlockScalarValue(token, source);
          break;
        case '"':
          setFlowScalarValue(token, source, "double-quoted-scalar");
          break;
        case "'":
          setFlowScalarValue(token, source, "single-quoted-scalar");
          break;
        default:
          setFlowScalarValue(token, source, "scalar");
      }
    }
    function setBlockScalarValue(token, source) {
      const he = source.indexOf("\n");
      const head = source.substring(0, he);
      const body = source.substring(he + 1) + "\n";
      if (token.type === "block-scalar") {
        const header = token.props[0];
        if (header.type !== "block-scalar-header")
          throw new Error("Invalid block scalar header");
        header.source = head;
        token.source = body;
      } else {
        const { offset } = token;
        const indent = "indent" in token ? token.indent : -1;
        const props = [
          { type: "block-scalar-header", offset, indent, source: head }
        ];
        if (!addEndtoBlockProps(props, "end" in token ? token.end : void 0))
          props.push({ type: "newline", offset: -1, indent, source: "\n" });
        for (const key of Object.keys(token))
          if (key !== "type" && key !== "offset")
            delete token[key];
        Object.assign(token, { type: "block-scalar", indent, props, source: body });
      }
    }
    function addEndtoBlockProps(props, end) {
      if (end)
        for (const st of end)
          switch (st.type) {
            case "space":
            case "comment":
              props.push(st);
              break;
            case "newline":
              props.push(st);
              return true;
          }
      return false;
    }
    function setFlowScalarValue(token, source, type) {
      switch (token.type) {
        case "scalar":
        case "double-quoted-scalar":
        case "single-quoted-scalar":
          token.type = type;
          token.source = source;
          break;
        case "block-scalar": {
          const end = token.props.slice(1);
          let oa = source.length;
          if (token.props[0].type === "block-scalar-header")
            oa -= token.props[0].source.length;
          for (const tok of end)
            tok.offset += oa;
          delete token.props;
          Object.assign(token, { type, source, end });
          break;
        }
        case "block-map":
        case "block-seq": {
          const offset = token.offset + source.length;
          const nl = { type: "newline", offset, indent: token.indent, source: "\n" };
          delete token.items;
          Object.assign(token, { type, source, end: [nl] });
          break;
        }
        default: {
          const indent = "indent" in token ? token.indent : -1;
          const end = "end" in token && Array.isArray(token.end) ? token.end.filter((st) => st.type === "space" || st.type === "comment" || st.type === "newline") : [];
          for (const key of Object.keys(token))
            if (key !== "type" && key !== "offset")
              delete token[key];
          Object.assign(token, { type, indent, source, end });
        }
      }
    }
    exports.createScalarToken = createScalarToken;
    exports.resolveAsScalar = resolveAsScalar;
    exports.setScalarValue = setScalarValue;
  }
});

// node_modules/yaml/dist/parse/cst-stringify.js
var require_cst_stringify = __commonJS({
  "node_modules/yaml/dist/parse/cst-stringify.js"(exports) {
    "use strict";
    var stringify = (cst) => "type" in cst ? stringifyToken(cst) : stringifyItem(cst);
    function stringifyToken(token) {
      switch (token.type) {
        case "block-scalar": {
          let res = "";
          for (const tok of token.props)
            res += stringifyToken(tok);
          return res + token.source;
        }
        case "block-map":
        case "block-seq": {
          let res = "";
          for (const item of token.items)
            res += stringifyItem(item);
          return res;
        }
        case "flow-collection": {
          let res = token.start.source;
          for (const item of token.items)
            res += stringifyItem(item);
          for (const st of token.end)
            res += st.source;
          return res;
        }
        case "document": {
          let res = stringifyItem(token);
          if (token.end)
            for (const st of token.end)
              res += st.source;
          return res;
        }
        default: {
          let res = token.source;
          if ("end" in token && token.end)
            for (const st of token.end)
              res += st.source;
          return res;
        }
      }
    }
    function stringifyItem({ start, key, sep: sep10, value }) {
      let res = "";
      for (const st of start)
        res += st.source;
      if (key)
        res += stringifyToken(key);
      if (sep10)
        for (const st of sep10)
          res += st.source;
      if (value)
        res += stringifyToken(value);
      return res;
    }
    exports.stringify = stringify;
  }
});

// node_modules/yaml/dist/parse/cst-visit.js
var require_cst_visit = __commonJS({
  "node_modules/yaml/dist/parse/cst-visit.js"(exports) {
    "use strict";
    var BREAK = /* @__PURE__ */ Symbol("break visit");
    var SKIP = /* @__PURE__ */ Symbol("skip children");
    var REMOVE = /* @__PURE__ */ Symbol("remove item");
    function visit(cst, visitor) {
      if ("type" in cst && cst.type === "document")
        cst = { start: cst.start, value: cst.value };
      _visit(Object.freeze([]), cst, visitor);
    }
    visit.BREAK = BREAK;
    visit.SKIP = SKIP;
    visit.REMOVE = REMOVE;
    visit.itemAtPath = (cst, path34) => {
      let item = cst;
      for (const [field, index] of path34) {
        const tok = item?.[field];
        if (tok && "items" in tok) {
          item = tok.items[index];
        } else
          return void 0;
      }
      return item;
    };
    visit.parentCollection = (cst, path34) => {
      const parent = visit.itemAtPath(cst, path34.slice(0, -1));
      const field = path34[path34.length - 1][0];
      const coll = parent?.[field];
      if (coll && "items" in coll)
        return coll;
      throw new Error("Parent collection not found");
    };
    function _visit(path34, item, visitor) {
      let ctrl = visitor(item, path34);
      if (typeof ctrl === "symbol")
        return ctrl;
      for (const field of ["key", "value"]) {
        const token = item[field];
        if (token && "items" in token) {
          for (let i = 0; i < token.items.length; ++i) {
            const ci = _visit(Object.freeze(path34.concat([[field, i]])), token.items[i], visitor);
            if (typeof ci === "number")
              i = ci - 1;
            else if (ci === BREAK)
              return BREAK;
            else if (ci === REMOVE) {
              token.items.splice(i, 1);
              i -= 1;
            }
          }
          if (typeof ctrl === "function" && field === "key")
            ctrl = ctrl(item, path34);
        }
      }
      return typeof ctrl === "function" ? ctrl(item, path34) : ctrl;
    }
    exports.visit = visit;
  }
});

// node_modules/yaml/dist/parse/cst.js
var require_cst = __commonJS({
  "node_modules/yaml/dist/parse/cst.js"(exports) {
    "use strict";
    var cstScalar = require_cst_scalar();
    var cstStringify = require_cst_stringify();
    var cstVisit = require_cst_visit();
    var BOM = "\uFEFF";
    var DOCUMENT = "";
    var FLOW_END = "";
    var SCALAR = "";
    var isCollection = (token) => !!token && "items" in token;
    var isScalar2 = (token) => !!token && (token.type === "scalar" || token.type === "single-quoted-scalar" || token.type === "double-quoted-scalar" || token.type === "block-scalar");
    function prettyToken(token) {
      switch (token) {
        case BOM:
          return "<BOM>";
        case DOCUMENT:
          return "<DOC>";
        case FLOW_END:
          return "<FLOW_END>";
        case SCALAR:
          return "<SCALAR>";
        default:
          return JSON.stringify(token);
      }
    }
    function tokenType(source) {
      switch (source) {
        case BOM:
          return "byte-order-mark";
        case DOCUMENT:
          return "doc-mode";
        case FLOW_END:
          return "flow-error-end";
        case SCALAR:
          return "scalar";
        case "---":
          return "doc-start";
        case "...":
          return "doc-end";
        case "":
        case "\n":
        case "\r\n":
          return "newline";
        case "-":
          return "seq-item-ind";
        case "?":
          return "explicit-key-ind";
        case ":":
          return "map-value-ind";
        case "{":
          return "flow-map-start";
        case "}":
          return "flow-map-end";
        case "[":
          return "flow-seq-start";
        case "]":
          return "flow-seq-end";
        case ",":
          return "comma";
      }
      switch (source[0]) {
        case " ":
        case "	":
          return "space";
        case "#":
          return "comment";
        case "%":
          return "directive-line";
        case "*":
          return "alias";
        case "&":
          return "anchor";
        case "!":
          return "tag";
        case "'":
          return "single-quoted-scalar";
        case '"':
          return "double-quoted-scalar";
        case "|":
        case ">":
          return "block-scalar-header";
      }
      return null;
    }
    exports.createScalarToken = cstScalar.createScalarToken;
    exports.resolveAsScalar = cstScalar.resolveAsScalar;
    exports.setScalarValue = cstScalar.setScalarValue;
    exports.stringify = cstStringify.stringify;
    exports.visit = cstVisit.visit;
    exports.BOM = BOM;
    exports.DOCUMENT = DOCUMENT;
    exports.FLOW_END = FLOW_END;
    exports.SCALAR = SCALAR;
    exports.isCollection = isCollection;
    exports.isScalar = isScalar2;
    exports.prettyToken = prettyToken;
    exports.tokenType = tokenType;
  }
});

// node_modules/yaml/dist/parse/lexer.js
var require_lexer = __commonJS({
  "node_modules/yaml/dist/parse/lexer.js"(exports) {
    "use strict";
    var cst = require_cst();
    function isEmpty(ch) {
      switch (ch) {
        case void 0:
        case " ":
        case "\n":
        case "\r":
        case "	":
          return true;
        default:
          return false;
      }
    }
    var hexDigits = new Set("0123456789ABCDEFabcdef");
    var tagChars = new Set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-#;/?:@&=+$_.!~*'()");
    var flowIndicatorChars = new Set(",[]{}");
    var invalidAnchorChars = new Set(" ,[]{}\n\r	");
    var isNotAnchorChar = (ch) => !ch || invalidAnchorChars.has(ch);
    var Lexer = class {
      constructor() {
        this.atEnd = false;
        this.blockScalarIndent = -1;
        this.blockScalarKeep = false;
        this.buffer = "";
        this.flowKey = false;
        this.flowLevel = 0;
        this.indentNext = 0;
        this.indentValue = 0;
        this.lineEndPos = null;
        this.next = null;
        this.pos = 0;
      }
      /**
       * Generate YAML tokens from the `source` string. If `incomplete`,
       * a part of the last line may be left as a buffer for the next call.
       *
       * @returns A generator of lexical tokens
       */
      *lex(source, incomplete = false) {
        if (source) {
          if (typeof source !== "string")
            throw TypeError("source is not a string");
          this.buffer = this.buffer ? this.buffer + source : source;
          this.lineEndPos = null;
        }
        this.atEnd = !incomplete;
        let next = this.next ?? "stream";
        while (next && (incomplete || this.hasChars(1)))
          next = yield* this.parseNext(next);
      }
      atLineEnd() {
        let i = this.pos;
        let ch = this.buffer[i];
        while (ch === " " || ch === "	")
          ch = this.buffer[++i];
        if (!ch || ch === "#" || ch === "\n")
          return true;
        if (ch === "\r")
          return this.buffer[i + 1] === "\n";
        return false;
      }
      charAt(n) {
        return this.buffer[this.pos + n];
      }
      continueScalar(offset) {
        let ch = this.buffer[offset];
        if (this.indentNext > 0) {
          let indent = 0;
          while (ch === " ")
            ch = this.buffer[++indent + offset];
          if (ch === "\r") {
            const next = this.buffer[indent + offset + 1];
            if (next === "\n" || !next && !this.atEnd)
              return offset + indent + 1;
          }
          return ch === "\n" || indent >= this.indentNext || !ch && !this.atEnd ? offset + indent : -1;
        }
        if (ch === "-" || ch === ".") {
          const dt = this.buffer.substr(offset, 3);
          if ((dt === "---" || dt === "...") && isEmpty(this.buffer[offset + 3]))
            return -1;
        }
        return offset;
      }
      getLine() {
        let end = this.lineEndPos;
        if (typeof end !== "number" || end !== -1 && end < this.pos) {
          end = this.buffer.indexOf("\n", this.pos);
          this.lineEndPos = end;
        }
        if (end === -1)
          return this.atEnd ? this.buffer.substring(this.pos) : null;
        if (this.buffer[end - 1] === "\r")
          end -= 1;
        return this.buffer.substring(this.pos, end);
      }
      hasChars(n) {
        return this.pos + n <= this.buffer.length;
      }
      setNext(state) {
        this.buffer = this.buffer.substring(this.pos);
        this.pos = 0;
        this.lineEndPos = null;
        this.next = state;
        return null;
      }
      peek(n) {
        return this.buffer.substr(this.pos, n);
      }
      *parseNext(next) {
        switch (next) {
          case "stream":
            return yield* this.parseStream();
          case "line-start":
            return yield* this.parseLineStart();
          case "block-start":
            return yield* this.parseBlockStart();
          case "doc":
            return yield* this.parseDocument();
          case "flow":
            return yield* this.parseFlowCollection();
          case "quoted-scalar":
            return yield* this.parseQuotedScalar();
          case "block-scalar":
            return yield* this.parseBlockScalar();
          case "plain-scalar":
            return yield* this.parsePlainScalar();
        }
      }
      *parseStream() {
        let line = this.getLine();
        if (line === null)
          return this.setNext("stream");
        if (line[0] === cst.BOM) {
          yield* this.pushCount(1);
          line = line.substring(1);
        }
        if (line[0] === "%") {
          let dirEnd = line.length;
          let cs = line.indexOf("#");
          while (cs !== -1) {
            const ch = line[cs - 1];
            if (ch === " " || ch === "	") {
              dirEnd = cs - 1;
              break;
            } else {
              cs = line.indexOf("#", cs + 1);
            }
          }
          while (true) {
            const ch = line[dirEnd - 1];
            if (ch === " " || ch === "	")
              dirEnd -= 1;
            else
              break;
          }
          const n = (yield* this.pushCount(dirEnd)) + (yield* this.pushSpaces(true));
          yield* this.pushCount(line.length - n);
          this.pushNewline();
          return "stream";
        }
        if (this.atLineEnd()) {
          const sp = yield* this.pushSpaces(true);
          yield* this.pushCount(line.length - sp);
          yield* this.pushNewline();
          return "stream";
        }
        yield cst.DOCUMENT;
        return yield* this.parseLineStart();
      }
      *parseLineStart() {
        const ch = this.charAt(0);
        if (!ch && !this.atEnd)
          return this.setNext("line-start");
        if (ch === "-" || ch === ".") {
          if (!this.atEnd && !this.hasChars(4))
            return this.setNext("line-start");
          const s = this.peek(3);
          if ((s === "---" || s === "...") && isEmpty(this.charAt(3))) {
            yield* this.pushCount(3);
            this.indentValue = 0;
            this.indentNext = 0;
            return s === "---" ? "doc" : "stream";
          }
        }
        this.indentValue = yield* this.pushSpaces(false);
        if (this.indentNext > this.indentValue && !isEmpty(this.charAt(1)))
          this.indentNext = this.indentValue;
        return yield* this.parseBlockStart();
      }
      *parseBlockStart() {
        const [ch0, ch1] = this.peek(2);
        if (!ch1 && !this.atEnd)
          return this.setNext("block-start");
        if ((ch0 === "-" || ch0 === "?" || ch0 === ":") && isEmpty(ch1)) {
          const n = (yield* this.pushCount(1)) + (yield* this.pushSpaces(true));
          this.indentNext = this.indentValue + 1;
          this.indentValue += n;
          return "block-start";
        }
        return "doc";
      }
      *parseDocument() {
        yield* this.pushSpaces(true);
        const line = this.getLine();
        if (line === null)
          return this.setNext("doc");
        let n = yield* this.pushIndicators();
        switch (line[n]) {
          case "#":
            yield* this.pushCount(line.length - n);
          // fallthrough
          case void 0:
            yield* this.pushNewline();
            return yield* this.parseLineStart();
          case "{":
          case "[":
            yield* this.pushCount(1);
            this.flowKey = false;
            this.flowLevel = 1;
            return "flow";
          case "}":
          case "]":
            yield* this.pushCount(1);
            return "doc";
          case "*":
            yield* this.pushUntil(isNotAnchorChar);
            return "doc";
          case '"':
          case "'":
            return yield* this.parseQuotedScalar();
          case "|":
          case ">":
            n += yield* this.parseBlockScalarHeader();
            n += yield* this.pushSpaces(true);
            yield* this.pushCount(line.length - n);
            yield* this.pushNewline();
            return yield* this.parseBlockScalar();
          default:
            return yield* this.parsePlainScalar();
        }
      }
      *parseFlowCollection() {
        let nl, sp;
        let indent = -1;
        do {
          nl = yield* this.pushNewline();
          if (nl > 0) {
            sp = yield* this.pushSpaces(false);
            this.indentValue = indent = sp;
          } else {
            sp = 0;
          }
          sp += yield* this.pushSpaces(true);
        } while (nl + sp > 0);
        const line = this.getLine();
        if (line === null)
          return this.setNext("flow");
        if (indent !== -1 && indent < this.indentNext && line[0] !== "#" || indent === 0 && (line.startsWith("---") || line.startsWith("...")) && isEmpty(line[3])) {
          const atFlowEndMarker = indent === this.indentNext - 1 && this.flowLevel === 1 && (line[0] === "]" || line[0] === "}");
          if (!atFlowEndMarker) {
            this.flowLevel = 0;
            yield cst.FLOW_END;
            return yield* this.parseLineStart();
          }
        }
        let n = 0;
        while (line[n] === ",") {
          n += yield* this.pushCount(1);
          n += yield* this.pushSpaces(true);
          this.flowKey = false;
        }
        n += yield* this.pushIndicators();
        switch (line[n]) {
          case void 0:
            return "flow";
          case "#":
            yield* this.pushCount(line.length - n);
            return "flow";
          case "{":
          case "[":
            yield* this.pushCount(1);
            this.flowKey = false;
            this.flowLevel += 1;
            return "flow";
          case "}":
          case "]":
            yield* this.pushCount(1);
            this.flowKey = true;
            this.flowLevel -= 1;
            return this.flowLevel ? "flow" : "doc";
          case "*":
            yield* this.pushUntil(isNotAnchorChar);
            return "flow";
          case '"':
          case "'":
            this.flowKey = true;
            return yield* this.parseQuotedScalar();
          case ":": {
            const next = this.charAt(1);
            if (this.flowKey || isEmpty(next) || next === ",") {
              this.flowKey = false;
              yield* this.pushCount(1);
              yield* this.pushSpaces(true);
              return "flow";
            }
          }
          // fallthrough
          default:
            this.flowKey = false;
            return yield* this.parsePlainScalar();
        }
      }
      *parseQuotedScalar() {
        const quote = this.charAt(0);
        let end = this.buffer.indexOf(quote, this.pos + 1);
        if (quote === "'") {
          while (end !== -1 && this.buffer[end + 1] === "'")
            end = this.buffer.indexOf("'", end + 2);
        } else {
          while (end !== -1) {
            let n = 0;
            while (this.buffer[end - 1 - n] === "\\")
              n += 1;
            if (n % 2 === 0)
              break;
            end = this.buffer.indexOf('"', end + 1);
          }
        }
        const qb = this.buffer.substring(0, end);
        let nl = qb.indexOf("\n", this.pos);
        if (nl !== -1) {
          while (nl !== -1) {
            const cs = this.continueScalar(nl + 1);
            if (cs === -1)
              break;
            nl = qb.indexOf("\n", cs);
          }
          if (nl !== -1) {
            end = nl - (qb[nl - 1] === "\r" ? 2 : 1);
          }
        }
        if (end === -1) {
          if (!this.atEnd)
            return this.setNext("quoted-scalar");
          end = this.buffer.length;
        }
        yield* this.pushToIndex(end + 1, false);
        return this.flowLevel ? "flow" : "doc";
      }
      *parseBlockScalarHeader() {
        this.blockScalarIndent = -1;
        this.blockScalarKeep = false;
        let i = this.pos;
        while (true) {
          const ch = this.buffer[++i];
          if (ch === "+")
            this.blockScalarKeep = true;
          else if (ch > "0" && ch <= "9")
            this.blockScalarIndent = Number(ch) - 1;
          else if (ch !== "-")
            break;
        }
        return yield* this.pushUntil((ch) => isEmpty(ch) || ch === "#");
      }
      *parseBlockScalar() {
        let nl = this.pos - 1;
        let indent = 0;
        let ch;
        loop: for (let i2 = this.pos; ch = this.buffer[i2]; ++i2) {
          switch (ch) {
            case " ":
              indent += 1;
              break;
            case "\n":
              nl = i2;
              indent = 0;
              break;
            case "\r": {
              const next = this.buffer[i2 + 1];
              if (!next && !this.atEnd)
                return this.setNext("block-scalar");
              if (next === "\n")
                break;
            }
            // fallthrough
            default:
              break loop;
          }
        }
        if (!ch && !this.atEnd)
          return this.setNext("block-scalar");
        if (indent >= this.indentNext) {
          if (this.blockScalarIndent === -1)
            this.indentNext = indent;
          else {
            this.indentNext = this.blockScalarIndent + (this.indentNext === 0 ? 1 : this.indentNext);
          }
          do {
            const cs = this.continueScalar(nl + 1);
            if (cs === -1)
              break;
            nl = this.buffer.indexOf("\n", cs);
          } while (nl !== -1);
          if (nl === -1) {
            if (!this.atEnd)
              return this.setNext("block-scalar");
            nl = this.buffer.length;
          }
        }
        let i = nl + 1;
        ch = this.buffer[i];
        while (ch === " ")
          ch = this.buffer[++i];
        if (ch === "	") {
          while (ch === "	" || ch === " " || ch === "\r" || ch === "\n")
            ch = this.buffer[++i];
          nl = i - 1;
        } else if (!this.blockScalarKeep) {
          do {
            let i2 = nl - 1;
            let ch2 = this.buffer[i2];
            if (ch2 === "\r")
              ch2 = this.buffer[--i2];
            const lastChar = i2;
            while (ch2 === " ")
              ch2 = this.buffer[--i2];
            if (ch2 === "\n" && i2 >= this.pos && i2 + 1 + indent > lastChar)
              nl = i2;
            else
              break;
          } while (true);
        }
        yield cst.SCALAR;
        yield* this.pushToIndex(nl + 1, true);
        return yield* this.parseLineStart();
      }
      *parsePlainScalar() {
        const inFlow = this.flowLevel > 0;
        let end = this.pos - 1;
        let i = this.pos - 1;
        let ch;
        while (ch = this.buffer[++i]) {
          if (ch === ":") {
            const next = this.buffer[i + 1];
            if (isEmpty(next) || inFlow && flowIndicatorChars.has(next))
              break;
            end = i;
          } else if (isEmpty(ch)) {
            let next = this.buffer[i + 1];
            if (ch === "\r") {
              if (next === "\n") {
                i += 1;
                ch = "\n";
                next = this.buffer[i + 1];
              } else
                end = i;
            }
            if (next === "#" || inFlow && flowIndicatorChars.has(next))
              break;
            if (ch === "\n") {
              const cs = this.continueScalar(i + 1);
              if (cs === -1)
                break;
              i = Math.max(i, cs - 2);
            }
          } else {
            if (inFlow && flowIndicatorChars.has(ch))
              break;
            end = i;
          }
        }
        if (!ch && !this.atEnd)
          return this.setNext("plain-scalar");
        yield cst.SCALAR;
        yield* this.pushToIndex(end + 1, true);
        return inFlow ? "flow" : "doc";
      }
      *pushCount(n) {
        if (n > 0) {
          yield this.buffer.substr(this.pos, n);
          this.pos += n;
          return n;
        }
        return 0;
      }
      *pushToIndex(i, allowEmpty) {
        const s = this.buffer.slice(this.pos, i);
        if (s) {
          yield s;
          this.pos += s.length;
          return s.length;
        } else if (allowEmpty)
          yield "";
        return 0;
      }
      *pushIndicators() {
        let n = 0;
        loop: while (true) {
          switch (this.charAt(0)) {
            case "!":
              n += yield* this.pushTag();
              n += yield* this.pushSpaces(true);
              continue loop;
            case "&":
              n += yield* this.pushUntil(isNotAnchorChar);
              n += yield* this.pushSpaces(true);
              continue loop;
            case "-":
            // this is an error
            case "?":
            // this is an error outside flow collections
            case ":": {
              const inFlow = this.flowLevel > 0;
              const ch1 = this.charAt(1);
              if (isEmpty(ch1) || inFlow && flowIndicatorChars.has(ch1)) {
                if (!inFlow)
                  this.indentNext = this.indentValue + 1;
                else if (this.flowKey)
                  this.flowKey = false;
                n += yield* this.pushCount(1);
                n += yield* this.pushSpaces(true);
                continue loop;
              }
            }
          }
          break loop;
        }
        return n;
      }
      *pushTag() {
        if (this.charAt(1) === "<") {
          let i = this.pos + 2;
          let ch = this.buffer[i];
          while (!isEmpty(ch) && ch !== ">")
            ch = this.buffer[++i];
          return yield* this.pushToIndex(ch === ">" ? i + 1 : i, false);
        } else {
          let i = this.pos + 1;
          let ch = this.buffer[i];
          while (ch) {
            if (tagChars.has(ch))
              ch = this.buffer[++i];
            else if (ch === "%" && hexDigits.has(this.buffer[i + 1]) && hexDigits.has(this.buffer[i + 2])) {
              ch = this.buffer[i += 3];
            } else
              break;
          }
          return yield* this.pushToIndex(i, false);
        }
      }
      *pushNewline() {
        const ch = this.buffer[this.pos];
        if (ch === "\n")
          return yield* this.pushCount(1);
        else if (ch === "\r" && this.charAt(1) === "\n")
          return yield* this.pushCount(2);
        else
          return 0;
      }
      *pushSpaces(allowTabs) {
        let i = this.pos - 1;
        let ch;
        do {
          ch = this.buffer[++i];
        } while (ch === " " || allowTabs && ch === "	");
        const n = i - this.pos;
        if (n > 0) {
          yield this.buffer.substr(this.pos, n);
          this.pos = i;
        }
        return n;
      }
      *pushUntil(test) {
        let i = this.pos;
        let ch = this.buffer[i];
        while (!test(ch))
          ch = this.buffer[++i];
        return yield* this.pushToIndex(i, false);
      }
    };
    exports.Lexer = Lexer;
  }
});

// node_modules/yaml/dist/parse/line-counter.js
var require_line_counter = __commonJS({
  "node_modules/yaml/dist/parse/line-counter.js"(exports) {
    "use strict";
    var LineCounter = class {
      constructor() {
        this.lineStarts = [];
        this.addNewLine = (offset) => this.lineStarts.push(offset);
        this.linePos = (offset) => {
          let low = 0;
          let high = this.lineStarts.length;
          while (low < high) {
            const mid = low + high >> 1;
            if (this.lineStarts[mid] < offset)
              low = mid + 1;
            else
              high = mid;
          }
          if (this.lineStarts[low] === offset)
            return { line: low + 1, col: 1 };
          if (low === 0)
            return { line: 0, col: offset };
          const start = this.lineStarts[low - 1];
          return { line: low, col: offset - start + 1 };
        };
      }
    };
    exports.LineCounter = LineCounter;
  }
});

// node_modules/yaml/dist/parse/parser.js
var require_parser = __commonJS({
  "node_modules/yaml/dist/parse/parser.js"(exports) {
    "use strict";
    var node_process = __require("process");
    var cst = require_cst();
    var lexer = require_lexer();
    function includesToken(list, type) {
      for (let i = 0; i < list.length; ++i)
        if (list[i].type === type)
          return true;
      return false;
    }
    function findNonEmptyIndex(list) {
      for (let i = 0; i < list.length; ++i) {
        switch (list[i].type) {
          case "space":
          case "comment":
          case "newline":
            break;
          default:
            return i;
        }
      }
      return -1;
    }
    function isFlowToken(token) {
      switch (token?.type) {
        case "alias":
        case "scalar":
        case "single-quoted-scalar":
        case "double-quoted-scalar":
        case "flow-collection":
          return true;
        default:
          return false;
      }
    }
    function getPrevProps(parent) {
      switch (parent.type) {
        case "document":
          return parent.start;
        case "block-map": {
          const it = parent.items[parent.items.length - 1];
          return it.sep ?? it.start;
        }
        case "block-seq":
          return parent.items[parent.items.length - 1].start;
        /* istanbul ignore next should not happen */
        default:
          return [];
      }
    }
    function getFirstKeyStartProps(prev) {
      if (prev.length === 0)
        return [];
      let i = prev.length;
      loop: while (--i >= 0) {
        switch (prev[i].type) {
          case "doc-start":
          case "explicit-key-ind":
          case "map-value-ind":
          case "seq-item-ind":
          case "newline":
            break loop;
        }
      }
      while (prev[++i]?.type === "space") {
      }
      return prev.splice(i, prev.length);
    }
    function arrayPushArray(target, source) {
      if (source.length < 1e5)
        Array.prototype.push.apply(target, source);
      else
        for (let i = 0; i < source.length; ++i)
          target.push(source[i]);
    }
    function fixFlowSeqItems(fc) {
      if (fc.start.type === "flow-seq-start") {
        for (const it of fc.items) {
          if (it.sep && !it.value && !includesToken(it.start, "explicit-key-ind") && !includesToken(it.sep, "map-value-ind")) {
            if (it.key)
              it.value = it.key;
            delete it.key;
            if (isFlowToken(it.value)) {
              if (it.value.end)
                arrayPushArray(it.value.end, it.sep);
              else
                it.value.end = it.sep;
            } else
              arrayPushArray(it.start, it.sep);
            delete it.sep;
          }
        }
      }
    }
    var Parser = class {
      /**
       * @param onNewLine - If defined, called separately with the start position of
       *   each new line (in `parse()`, including the start of input).
       */
      constructor(onNewLine) {
        this.atNewLine = true;
        this.atScalar = false;
        this.indent = 0;
        this.offset = 0;
        this.onKeyLine = false;
        this.stack = [];
        this.source = "";
        this.type = "";
        this.lexer = new lexer.Lexer();
        this.onNewLine = onNewLine;
      }
      /**
       * Parse `source` as a YAML stream.
       * If `incomplete`, a part of the last line may be left as a buffer for the next call.
       *
       * Errors are not thrown, but yielded as `{ type: 'error', message }` tokens.
       *
       * @returns A generator of tokens representing each directive, document, and other structure.
       */
      *parse(source, incomplete = false) {
        if (this.onNewLine && this.offset === 0)
          this.onNewLine(0);
        for (const lexeme of this.lexer.lex(source, incomplete))
          yield* this.next(lexeme);
        if (!incomplete)
          yield* this.end();
      }
      /**
       * Advance the parser by the `source` of one lexical token.
       */
      *next(source) {
        this.source = source;
        if (node_process.env.LOG_TOKENS)
          console.log("|", cst.prettyToken(source));
        if (this.atScalar) {
          this.atScalar = false;
          yield* this.step();
          this.offset += source.length;
          return;
        }
        const type = cst.tokenType(source);
        if (!type) {
          const message = `Not a YAML token: ${source}`;
          yield* this.pop({ type: "error", offset: this.offset, message, source });
          this.offset += source.length;
        } else if (type === "scalar") {
          this.atNewLine = false;
          this.atScalar = true;
          this.type = "scalar";
        } else {
          this.type = type;
          yield* this.step();
          switch (type) {
            case "newline":
              this.atNewLine = true;
              this.indent = 0;
              if (this.onNewLine)
                this.onNewLine(this.offset + source.length);
              break;
            case "space":
              if (this.atNewLine && source[0] === " ")
                this.indent += source.length;
              break;
            case "explicit-key-ind":
            case "map-value-ind":
            case "seq-item-ind":
              if (this.atNewLine)
                this.indent += source.length;
              break;
            case "doc-mode":
            case "flow-error-end":
              return;
            default:
              this.atNewLine = false;
          }
          this.offset += source.length;
        }
      }
      /** Call at end of input to push out any remaining constructions */
      *end() {
        while (this.stack.length > 0)
          yield* this.pop();
      }
      get sourceToken() {
        const st = {
          type: this.type,
          offset: this.offset,
          indent: this.indent,
          source: this.source
        };
        return st;
      }
      *step() {
        const top = this.peek(1);
        if (this.type === "doc-end" && top?.type !== "doc-end") {
          while (this.stack.length > 0)
            yield* this.pop();
          this.stack.push({
            type: "doc-end",
            offset: this.offset,
            source: this.source
          });
          return;
        }
        if (!top)
          return yield* this.stream();
        switch (top.type) {
          case "document":
            return yield* this.document(top);
          case "alias":
          case "scalar":
          case "single-quoted-scalar":
          case "double-quoted-scalar":
            return yield* this.scalar(top);
          case "block-scalar":
            return yield* this.blockScalar(top);
          case "block-map":
            return yield* this.blockMap(top);
          case "block-seq":
            return yield* this.blockSequence(top);
          case "flow-collection":
            return yield* this.flowCollection(top);
          case "doc-end":
            return yield* this.documentEnd(top);
        }
        yield* this.pop();
      }
      peek(n) {
        return this.stack[this.stack.length - n];
      }
      *pop(error) {
        const token = error ?? this.stack.pop();
        if (!token) {
          const message = "Tried to pop an empty stack";
          yield { type: "error", offset: this.offset, source: "", message };
        } else if (this.stack.length === 0) {
          yield token;
        } else {
          const top = this.peek(1);
          if (token.type === "block-scalar") {
            token.indent = "indent" in top ? top.indent : 0;
          } else if (token.type === "flow-collection" && top.type === "document") {
            token.indent = 0;
          }
          if (token.type === "flow-collection")
            fixFlowSeqItems(token);
          switch (top.type) {
            case "document":
              top.value = token;
              break;
            case "block-scalar":
              top.props.push(token);
              break;
            case "block-map": {
              const it = top.items[top.items.length - 1];
              if (it.value) {
                top.items.push({ start: [], key: token, sep: [] });
                this.onKeyLine = true;
                return;
              } else if (it.sep) {
                it.value = token;
              } else {
                Object.assign(it, { key: token, sep: [] });
                this.onKeyLine = !it.explicitKey;
                return;
              }
              break;
            }
            case "block-seq": {
              const it = top.items[top.items.length - 1];
              if (it.value)
                top.items.push({ start: [], value: token });
              else
                it.value = token;
              break;
            }
            case "flow-collection": {
              const it = top.items[top.items.length - 1];
              if (!it || it.value)
                top.items.push({ start: [], key: token, sep: [] });
              else if (it.sep)
                it.value = token;
              else
                Object.assign(it, { key: token, sep: [] });
              return;
            }
            /* istanbul ignore next should not happen */
            default:
              yield* this.pop();
              yield* this.pop(token);
          }
          if ((top.type === "document" || top.type === "block-map" || top.type === "block-seq") && (token.type === "block-map" || token.type === "block-seq")) {
            const last = token.items[token.items.length - 1];
            if (last && !last.sep && !last.value && last.start.length > 0 && findNonEmptyIndex(last.start) === -1 && (token.indent === 0 || last.start.every((st) => st.type !== "comment" || st.indent < token.indent))) {
              if (top.type === "document")
                top.end = last.start;
              else
                top.items.push({ start: last.start });
              token.items.splice(-1, 1);
            }
          }
        }
      }
      *stream() {
        switch (this.type) {
          case "directive-line":
            yield { type: "directive", offset: this.offset, source: this.source };
            return;
          case "byte-order-mark":
          case "space":
          case "comment":
          case "newline":
            yield this.sourceToken;
            return;
          case "doc-mode":
          case "doc-start": {
            const doc = {
              type: "document",
              offset: this.offset,
              start: []
            };
            if (this.type === "doc-start")
              doc.start.push(this.sourceToken);
            this.stack.push(doc);
            return;
          }
        }
        yield {
          type: "error",
          offset: this.offset,
          message: `Unexpected ${this.type} token in YAML stream`,
          source: this.source
        };
      }
      *document(doc) {
        if (doc.value)
          return yield* this.lineEnd(doc);
        switch (this.type) {
          case "doc-start": {
            if (findNonEmptyIndex(doc.start) !== -1) {
              yield* this.pop();
              yield* this.step();
            } else
              doc.start.push(this.sourceToken);
            return;
          }
          case "anchor":
          case "tag":
          case "space":
          case "comment":
          case "newline":
            doc.start.push(this.sourceToken);
            return;
        }
        const bv = this.startBlockValue(doc);
        if (bv)
          this.stack.push(bv);
        else {
          yield {
            type: "error",
            offset: this.offset,
            message: `Unexpected ${this.type} token in YAML document`,
            source: this.source
          };
        }
      }
      *scalar(scalar) {
        if (this.type === "map-value-ind") {
          const prev = getPrevProps(this.peek(2));
          const start = getFirstKeyStartProps(prev);
          let sep10;
          if (scalar.end) {
            sep10 = scalar.end;
            sep10.push(this.sourceToken);
            delete scalar.end;
          } else
            sep10 = [this.sourceToken];
          const map = {
            type: "block-map",
            offset: scalar.offset,
            indent: scalar.indent,
            items: [{ start, key: scalar, sep: sep10 }]
          };
          this.onKeyLine = true;
          this.stack[this.stack.length - 1] = map;
        } else
          yield* this.lineEnd(scalar);
      }
      *blockScalar(scalar) {
        switch (this.type) {
          case "space":
          case "comment":
          case "newline":
            scalar.props.push(this.sourceToken);
            return;
          case "scalar":
            scalar.source = this.source;
            this.atNewLine = true;
            this.indent = 0;
            if (this.onNewLine) {
              let nl = this.source.indexOf("\n") + 1;
              while (nl !== 0) {
                this.onNewLine(this.offset + nl);
                nl = this.source.indexOf("\n", nl) + 1;
              }
            }
            yield* this.pop();
            break;
          /* istanbul ignore next should not happen */
          default:
            yield* this.pop();
            yield* this.step();
        }
      }
      *blockMap(map) {
        const it = map.items[map.items.length - 1];
        switch (this.type) {
          case "newline":
            this.onKeyLine = false;
            if (it.value) {
              const end = "end" in it.value ? it.value.end : void 0;
              const last = Array.isArray(end) ? end[end.length - 1] : void 0;
              if (last?.type === "comment")
                end?.push(this.sourceToken);
              else
                map.items.push({ start: [this.sourceToken] });
            } else if (it.sep) {
              it.sep.push(this.sourceToken);
            } else {
              it.start.push(this.sourceToken);
            }
            return;
          case "space":
          case "comment":
            if (it.value) {
              map.items.push({ start: [this.sourceToken] });
            } else if (it.sep) {
              it.sep.push(this.sourceToken);
            } else {
              if (this.atIndentedComment(it.start, map.indent)) {
                const prev = map.items[map.items.length - 2];
                const end = prev?.value?.end;
                if (Array.isArray(end)) {
                  arrayPushArray(end, it.start);
                  end.push(this.sourceToken);
                  map.items.pop();
                  return;
                }
              }
              it.start.push(this.sourceToken);
            }
            return;
        }
        if (this.indent >= map.indent) {
          const atMapIndent = !this.onKeyLine && this.indent === map.indent;
          const atNextItem = atMapIndent && (it.sep || it.explicitKey) && this.type !== "seq-item-ind";
          let start = [];
          if (atNextItem && it.sep && !it.value) {
            const nl = [];
            for (let i = 0; i < it.sep.length; ++i) {
              const st = it.sep[i];
              switch (st.type) {
                case "newline":
                  nl.push(i);
                  break;
                case "space":
                  break;
                case "comment":
                  if (st.indent > map.indent)
                    nl.length = 0;
                  break;
                default:
                  nl.length = 0;
              }
            }
            if (nl.length >= 2)
              start = it.sep.splice(nl[1]);
          }
          switch (this.type) {
            case "anchor":
            case "tag":
              if (atNextItem || it.value) {
                start.push(this.sourceToken);
                map.items.push({ start });
                this.onKeyLine = true;
              } else if (it.sep) {
                it.sep.push(this.sourceToken);
              } else {
                it.start.push(this.sourceToken);
              }
              return;
            case "explicit-key-ind":
              if (!it.sep && !it.explicitKey) {
                it.start.push(this.sourceToken);
                it.explicitKey = true;
              } else if (atNextItem || it.value) {
                start.push(this.sourceToken);
                map.items.push({ start, explicitKey: true });
              } else {
                this.stack.push({
                  type: "block-map",
                  offset: this.offset,
                  indent: this.indent,
                  items: [{ start: [this.sourceToken], explicitKey: true }]
                });
              }
              this.onKeyLine = true;
              return;
            case "map-value-ind":
              if (it.explicitKey) {
                if (!it.sep) {
                  if (includesToken(it.start, "newline")) {
                    Object.assign(it, { key: null, sep: [this.sourceToken] });
                  } else {
                    const start2 = getFirstKeyStartProps(it.start);
                    this.stack.push({
                      type: "block-map",
                      offset: this.offset,
                      indent: this.indent,
                      items: [{ start: start2, key: null, sep: [this.sourceToken] }]
                    });
                  }
                } else if (it.value) {
                  map.items.push({ start: [], key: null, sep: [this.sourceToken] });
                } else if (includesToken(it.sep, "map-value-ind")) {
                  this.stack.push({
                    type: "block-map",
                    offset: this.offset,
                    indent: this.indent,
                    items: [{ start, key: null, sep: [this.sourceToken] }]
                  });
                } else if (isFlowToken(it.key) && !includesToken(it.sep, "newline")) {
                  const start2 = getFirstKeyStartProps(it.start);
                  const key = it.key;
                  const sep10 = it.sep;
                  sep10.push(this.sourceToken);
                  delete it.key;
                  delete it.sep;
                  this.stack.push({
                    type: "block-map",
                    offset: this.offset,
                    indent: this.indent,
                    items: [{ start: start2, key, sep: sep10 }]
                  });
                } else if (start.length > 0) {
                  it.sep = it.sep.concat(start, this.sourceToken);
                } else {
                  it.sep.push(this.sourceToken);
                }
              } else {
                if (!it.sep) {
                  Object.assign(it, { key: null, sep: [this.sourceToken] });
                } else if (it.value || atNextItem) {
                  map.items.push({ start, key: null, sep: [this.sourceToken] });
                } else if (includesToken(it.sep, "map-value-ind")) {
                  this.stack.push({
                    type: "block-map",
                    offset: this.offset,
                    indent: this.indent,
                    items: [{ start: [], key: null, sep: [this.sourceToken] }]
                  });
                } else {
                  it.sep.push(this.sourceToken);
                }
              }
              this.onKeyLine = true;
              return;
            case "alias":
            case "scalar":
            case "single-quoted-scalar":
            case "double-quoted-scalar": {
              const fs30 = this.flowScalar(this.type);
              if (atNextItem || it.value) {
                map.items.push({ start, key: fs30, sep: [] });
                this.onKeyLine = true;
              } else if (it.sep) {
                this.stack.push(fs30);
              } else {
                Object.assign(it, { key: fs30, sep: [] });
                this.onKeyLine = true;
              }
              return;
            }
            default: {
              const bv = this.startBlockValue(map);
              if (bv) {
                if (bv.type === "block-seq") {
                  if (!it.explicitKey && it.sep && !includesToken(it.sep, "newline")) {
                    yield* this.pop({
                      type: "error",
                      offset: this.offset,
                      message: "Unexpected block-seq-ind on same line with key",
                      source: this.source
                    });
                    return;
                  }
                } else if (atMapIndent) {
                  map.items.push({ start });
                }
                this.stack.push(bv);
                return;
              }
            }
          }
        }
        yield* this.pop();
        yield* this.step();
      }
      *blockSequence(seq) {
        const it = seq.items[seq.items.length - 1];
        switch (this.type) {
          case "newline":
            if (it.value) {
              const end = "end" in it.value ? it.value.end : void 0;
              const last = Array.isArray(end) ? end[end.length - 1] : void 0;
              if (last?.type === "comment")
                end?.push(this.sourceToken);
              else
                seq.items.push({ start: [this.sourceToken] });
            } else
              it.start.push(this.sourceToken);
            return;
          case "space":
          case "comment":
            if (it.value)
              seq.items.push({ start: [this.sourceToken] });
            else {
              if (this.atIndentedComment(it.start, seq.indent)) {
                const prev = seq.items[seq.items.length - 2];
                const end = prev?.value?.end;
                if (Array.isArray(end)) {
                  arrayPushArray(end, it.start);
                  end.push(this.sourceToken);
                  seq.items.pop();
                  return;
                }
              }
              it.start.push(this.sourceToken);
            }
            return;
          case "anchor":
          case "tag":
            if (it.value || this.indent <= seq.indent)
              break;
            it.start.push(this.sourceToken);
            return;
          case "seq-item-ind":
            if (this.indent !== seq.indent)
              break;
            if (it.value || includesToken(it.start, "seq-item-ind"))
              seq.items.push({ start: [this.sourceToken] });
            else
              it.start.push(this.sourceToken);
            return;
        }
        if (this.indent > seq.indent) {
          const bv = this.startBlockValue(seq);
          if (bv) {
            this.stack.push(bv);
            return;
          }
        }
        yield* this.pop();
        yield* this.step();
      }
      *flowCollection(fc) {
        const it = fc.items[fc.items.length - 1];
        if (this.type === "flow-error-end") {
          let top;
          do {
            yield* this.pop();
            top = this.peek(1);
          } while (top?.type === "flow-collection");
        } else if (fc.end.length === 0) {
          switch (this.type) {
            case "comma":
            case "explicit-key-ind":
              if (!it || it.sep)
                fc.items.push({ start: [this.sourceToken] });
              else
                it.start.push(this.sourceToken);
              return;
            case "map-value-ind":
              if (!it || it.value)
                fc.items.push({ start: [], key: null, sep: [this.sourceToken] });
              else if (it.sep)
                it.sep.push(this.sourceToken);
              else
                Object.assign(it, { key: null, sep: [this.sourceToken] });
              return;
            case "space":
            case "comment":
            case "newline":
            case "anchor":
            case "tag":
              if (!it || it.value)
                fc.items.push({ start: [this.sourceToken] });
              else if (it.sep)
                it.sep.push(this.sourceToken);
              else
                it.start.push(this.sourceToken);
              return;
            case "alias":
            case "scalar":
            case "single-quoted-scalar":
            case "double-quoted-scalar": {
              const fs30 = this.flowScalar(this.type);
              if (!it || it.value)
                fc.items.push({ start: [], key: fs30, sep: [] });
              else if (it.sep)
                this.stack.push(fs30);
              else
                Object.assign(it, { key: fs30, sep: [] });
              return;
            }
            case "flow-map-end":
            case "flow-seq-end":
              fc.end.push(this.sourceToken);
              return;
          }
          const bv = this.startBlockValue(fc);
          if (bv)
            this.stack.push(bv);
          else {
            yield* this.pop();
            yield* this.step();
          }
        } else {
          const parent = this.peek(2);
          if (parent.type === "block-map" && (this.type === "map-value-ind" && parent.indent === fc.indent || this.type === "newline" && !parent.items[parent.items.length - 1].sep)) {
            yield* this.pop();
            yield* this.step();
          } else if (this.type === "map-value-ind" && parent.type !== "flow-collection") {
            const prev = getPrevProps(parent);
            const start = getFirstKeyStartProps(prev);
            fixFlowSeqItems(fc);
            const sep10 = fc.end.splice(1, fc.end.length);
            sep10.push(this.sourceToken);
            const map = {
              type: "block-map",
              offset: fc.offset,
              indent: fc.indent,
              items: [{ start, key: fc, sep: sep10 }]
            };
            this.onKeyLine = true;
            this.stack[this.stack.length - 1] = map;
          } else {
            yield* this.lineEnd(fc);
          }
        }
      }
      flowScalar(type) {
        if (this.onNewLine) {
          let nl = this.source.indexOf("\n") + 1;
          while (nl !== 0) {
            this.onNewLine(this.offset + nl);
            nl = this.source.indexOf("\n", nl) + 1;
          }
        }
        return {
          type,
          offset: this.offset,
          indent: this.indent,
          source: this.source
        };
      }
      startBlockValue(parent) {
        switch (this.type) {
          case "alias":
          case "scalar":
          case "single-quoted-scalar":
          case "double-quoted-scalar":
            return this.flowScalar(this.type);
          case "block-scalar-header":
            return {
              type: "block-scalar",
              offset: this.offset,
              indent: this.indent,
              props: [this.sourceToken],
              source: ""
            };
          case "flow-map-start":
          case "flow-seq-start":
            return {
              type: "flow-collection",
              offset: this.offset,
              indent: this.indent,
              start: this.sourceToken,
              items: [],
              end: []
            };
          case "seq-item-ind":
            return {
              type: "block-seq",
              offset: this.offset,
              indent: this.indent,
              items: [{ start: [this.sourceToken] }]
            };
          case "explicit-key-ind": {
            this.onKeyLine = true;
            const prev = getPrevProps(parent);
            const start = getFirstKeyStartProps(prev);
            start.push(this.sourceToken);
            return {
              type: "block-map",
              offset: this.offset,
              indent: this.indent,
              items: [{ start, explicitKey: true }]
            };
          }
          case "map-value-ind": {
            this.onKeyLine = true;
            const prev = getPrevProps(parent);
            const start = getFirstKeyStartProps(prev);
            return {
              type: "block-map",
              offset: this.offset,
              indent: this.indent,
              items: [{ start, key: null, sep: [this.sourceToken] }]
            };
          }
        }
        return null;
      }
      atIndentedComment(start, indent) {
        if (this.type !== "comment")
          return false;
        if (this.indent <= indent)
          return false;
        return start.every((st) => st.type === "newline" || st.type === "space");
      }
      *documentEnd(docEnd) {
        if (this.type !== "doc-mode") {
          if (docEnd.end)
            docEnd.end.push(this.sourceToken);
          else
            docEnd.end = [this.sourceToken];
          if (this.type === "newline")
            yield* this.pop();
        }
      }
      *lineEnd(token) {
        switch (this.type) {
          case "comma":
          case "doc-start":
          case "doc-end":
          case "flow-seq-end":
          case "flow-map-end":
          case "map-value-ind":
            yield* this.pop();
            yield* this.step();
            break;
          case "newline":
            this.onKeyLine = false;
          // fallthrough
          case "space":
          case "comment":
          default:
            if (token.end)
              token.end.push(this.sourceToken);
            else
              token.end = [this.sourceToken];
            if (this.type === "newline")
              yield* this.pop();
        }
      }
    };
    exports.Parser = Parser;
  }
});

// node_modules/yaml/dist/public-api.js
var require_public_api = __commonJS({
  "node_modules/yaml/dist/public-api.js"(exports) {
    "use strict";
    var composer = require_composer();
    var Document = require_Document();
    var errors = require_errors();
    var log = require_log();
    var identity = require_identity();
    var lineCounter = require_line_counter();
    var parser = require_parser();
    function parseOptions(options) {
      const prettyErrors = options.prettyErrors !== false;
      const lineCounter$1 = options.lineCounter || prettyErrors && new lineCounter.LineCounter() || null;
      return { lineCounter: lineCounter$1, prettyErrors };
    }
    function parseAllDocuments(source, options = {}) {
      const { lineCounter: lineCounter2, prettyErrors } = parseOptions(options);
      const parser$1 = new parser.Parser(lineCounter2?.addNewLine);
      const composer$1 = new composer.Composer(options);
      const docs = Array.from(composer$1.compose(parser$1.parse(source)));
      if (prettyErrors && lineCounter2)
        for (const doc of docs) {
          doc.errors.forEach(errors.prettifyError(source, lineCounter2));
          doc.warnings.forEach(errors.prettifyError(source, lineCounter2));
        }
      if (docs.length > 0)
        return docs;
      return Object.assign([], { empty: true }, composer$1.streamInfo());
    }
    function parseDocument2(source, options = {}) {
      const { lineCounter: lineCounter2, prettyErrors } = parseOptions(options);
      const parser$1 = new parser.Parser(lineCounter2?.addNewLine);
      const composer$1 = new composer.Composer(options);
      let doc = null;
      for (const _doc of composer$1.compose(parser$1.parse(source), true, source.length)) {
        if (!doc)
          doc = _doc;
        else if (doc.options.logLevel !== "silent") {
          doc.errors.push(new errors.YAMLParseError(_doc.range.slice(0, 2), "MULTIPLE_DOCS", "Source contains multiple documents; please use YAML.parseAllDocuments()"));
          break;
        }
      }
      if (prettyErrors && lineCounter2) {
        doc.errors.forEach(errors.prettifyError(source, lineCounter2));
        doc.warnings.forEach(errors.prettifyError(source, lineCounter2));
      }
      return doc;
    }
    function parse3(src, reviver, options) {
      let _reviver = void 0;
      if (typeof reviver === "function") {
        _reviver = reviver;
      } else if (options === void 0 && reviver && typeof reviver === "object") {
        options = reviver;
      }
      const doc = parseDocument2(src, options);
      if (!doc)
        return null;
      doc.warnings.forEach((warning) => log.warn(doc.options.logLevel, warning));
      if (doc.errors.length > 0) {
        if (doc.options.logLevel !== "silent")
          throw doc.errors[0];
        else
          doc.errors = [];
      }
      return doc.toJS(Object.assign({ reviver: _reviver }, options));
    }
    function stringify(value, replacer, options) {
      let _replacer = null;
      if (typeof replacer === "function" || Array.isArray(replacer)) {
        _replacer = replacer;
      } else if (options === void 0 && replacer) {
        options = replacer;
      }
      if (typeof options === "string")
        options = options.length;
      if (typeof options === "number") {
        const indent = Math.round(options);
        options = indent < 1 ? void 0 : indent > 8 ? { indent: 8 } : { indent };
      }
      if (value === void 0) {
        const { keepUndefined } = options ?? replacer ?? {};
        if (!keepUndefined)
          return void 0;
      }
      if (identity.isDocument(value) && !_replacer)
        return value.toString(options);
      return new Document.Document(value, _replacer, options).toString(options);
    }
    exports.parse = parse3;
    exports.parseAllDocuments = parseAllDocuments;
    exports.parseDocument = parseDocument2;
    exports.stringify = stringify;
  }
});

// node_modules/yaml/dist/index.js
var require_dist = __commonJS({
  "node_modules/yaml/dist/index.js"(exports) {
    "use strict";
    var composer = require_composer();
    var Document = require_Document();
    var Schema = require_Schema();
    var errors = require_errors();
    var Alias = require_Alias();
    var identity = require_identity();
    var Pair = require_Pair();
    var Scalar = require_Scalar();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var cst = require_cst();
    var lexer = require_lexer();
    var lineCounter = require_line_counter();
    var parser = require_parser();
    var publicApi = require_public_api();
    var visit = require_visit();
    exports.Composer = composer.Composer;
    exports.Document = Document.Document;
    exports.Schema = Schema.Schema;
    exports.YAMLError = errors.YAMLError;
    exports.YAMLParseError = errors.YAMLParseError;
    exports.YAMLWarning = errors.YAMLWarning;
    exports.Alias = Alias.Alias;
    exports.isAlias = identity.isAlias;
    exports.isCollection = identity.isCollection;
    exports.isDocument = identity.isDocument;
    exports.isMap = identity.isMap;
    exports.isNode = identity.isNode;
    exports.isPair = identity.isPair;
    exports.isScalar = identity.isScalar;
    exports.isSeq = identity.isSeq;
    exports.Pair = Pair.Pair;
    exports.Scalar = Scalar.Scalar;
    exports.YAMLMap = YAMLMap.YAMLMap;
    exports.YAMLSeq = YAMLSeq.YAMLSeq;
    exports.CST = cst;
    exports.Lexer = lexer.Lexer;
    exports.LineCounter = lineCounter.LineCounter;
    exports.Parser = parser.Parser;
    exports.parse = publicApi.parse;
    exports.parseAllDocuments = publicApi.parseAllDocuments;
    exports.parseDocument = publicApi.parseDocument;
    exports.stringify = publicApi.stringify;
    exports.visit = visit.visit;
    exports.visitAsync = visit.visitAsync;
  }
});

// packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
import * as fs27 from "node:fs";
import * as path31 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts
import * as path29 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
import * as fs21 from "node:fs";
import * as os3 from "node:os";
import * as path25 from "node:path";

// node_modules/typebox/build/system/memory/memory.mjs
var memory_exports = {};
__export(memory_exports, {
  Assign: () => Assign,
  Clone: () => Clone,
  Create: () => Create,
  Discard: () => Discard,
  Metrics: () => Metrics,
  Update: () => Update
});

// node_modules/typebox/build/system/memory/metrics.mjs
var Metrics = {
  assign: 0,
  create: 0,
  clone: 0,
  discard: 0,
  update: 0
};

// node_modules/typebox/build/system/memory/assign.mjs
function Assign(left, right) {
  Metrics.assign += 1;
  return { ...left, ...right };
}

// node_modules/typebox/build/guard/guard.mjs
var guard_exports = {};
__export(guard_exports, {
  Entries: () => Entries,
  EntriesRegExp: () => EntriesRegExp,
  Every: () => Every,
  EveryAll: () => EveryAll,
  GraphemeCount: () => GraphemeCount2,
  HasPropertyKey: () => HasPropertyKey,
  IsArray: () => IsArray,
  IsBigInt: () => IsBigInt,
  IsBoolean: () => IsBoolean,
  IsClassInstance: () => IsClassInstance,
  IsConstructor: () => IsConstructor,
  IsDeepEqual: () => IsDeepEqual,
  IsEqual: () => IsEqual,
  IsFunction: () => IsFunction,
  IsGreaterEqualThan: () => IsGreaterEqualThan,
  IsGreaterThan: () => IsGreaterThan,
  IsInteger: () => IsInteger,
  IsLessEqualThan: () => IsLessEqualThan,
  IsLessThan: () => IsLessThan,
  IsMaxLength: () => IsMaxLength2,
  IsMinLength: () => IsMinLength2,
  IsMultipleOf: () => IsMultipleOf,
  IsNull: () => IsNull,
  IsNumber: () => IsNumber,
  IsObject: () => IsObject,
  IsObjectNotArray: () => IsObjectNotArray,
  IsString: () => IsString,
  IsSymbol: () => IsSymbol,
  IsUndefined: () => IsUndefined,
  IsUnsafePropertyKey: () => IsUnsafePropertyKey,
  IsValueLike: () => IsValueLike,
  Keys: () => Keys,
  ShiftLeft: () => ShiftLeft,
  Symbols: () => Symbols,
  Values: () => Values
});

// node_modules/typebox/build/guard/string.mjs
function IsBetween(value, min, max) {
  return value >= min && value <= max;
}
function IsZeroWidthJoiner(value) {
  return value === 8205;
}
function IsHighSurrogate(value) {
  return IsBetween(value, 55296, 56319);
}
function IsRegionalIndicator(value) {
  return IsBetween(value, 127462, 127487);
}
function IsVariationSelector(value) {
  return IsBetween(value, 65024, 65039);
}
function IsCombiningMark(value) {
  return IsBetween(value, 768, 879) || IsBetween(value, 6832, 6911) || IsBetween(value, 7616, 7679) || IsBetween(value, 65056, 65071);
}
function CodePointLength(value) {
  return value > 65535 ? 2 : 1;
}
function ConsumeModifiers(value, index) {
  while (index < value.length) {
    const point = value.codePointAt(index);
    if (IsCombiningMark(point) || IsVariationSelector(point)) {
      index += CodePointLength(point);
    } else {
      break;
    }
  }
  return index;
}
function NextGraphemeClusterIndex(value, clusterStart) {
  const startCP = value.codePointAt(clusterStart);
  let clusterEnd = clusterStart + CodePointLength(startCP);
  clusterEnd = ConsumeModifiers(value, clusterEnd);
  while (clusterEnd < value.length - 1 && value[clusterEnd] === "\u200D") {
    const nextCP = value.codePointAt(clusterEnd + 1);
    clusterEnd += 1 + CodePointLength(nextCP);
    clusterEnd = ConsumeModifiers(value, clusterEnd);
  }
  if (IsRegionalIndicator(startCP) && clusterEnd < value.length && IsRegionalIndicator(value.codePointAt(clusterEnd))) {
    clusterEnd += CodePointLength(value.codePointAt(clusterEnd));
  }
  return clusterEnd;
}
function IsGraphemeCodePoint(value) {
  return IsHighSurrogate(value) || IsCombiningMark(value) || IsVariationSelector(value) || IsZeroWidthJoiner(value);
}
function GraphemeCount(value) {
  let count2 = 0;
  let index = 0;
  while (index < value.length) {
    index = NextGraphemeClusterIndex(value, index);
    count2++;
  }
  return count2;
}
function IsMinLength(value, minLength) {
  if (minLength === 0)
    return true;
  let count2 = 0;
  let index = 0;
  while (index < value.length) {
    index = NextGraphemeClusterIndex(value, index);
    count2++;
    if (count2 >= minLength)
      return true;
  }
  return false;
}
function IsMaxLength(value, maxLength) {
  let count2 = 0;
  let index = 0;
  while (index < value.length) {
    index = NextGraphemeClusterIndex(value, index);
    count2++;
    if (count2 > maxLength)
      return false;
  }
  return true;
}
function IsMinLengthFast(value, minLength) {
  if (minLength === 0)
    return true;
  let index = 0;
  while (index < value.length) {
    if (IsGraphemeCodePoint(value.charCodeAt(index))) {
      return IsMinLength(value, minLength);
    }
    index++;
    if (index >= minLength)
      return true;
  }
  return false;
}
function IsMaxLengthFast(value, maxLength) {
  let index = 0;
  while (index < value.length) {
    if (IsGraphemeCodePoint(value.charCodeAt(index))) {
      return IsMaxLength(value, maxLength);
    }
    index++;
    if (index > maxLength)
      return false;
  }
  return true;
}

// node_modules/typebox/build/guard/guard.mjs
function IsArray(value) {
  return Array.isArray(value);
}
function IsBigInt(value) {
  return IsEqual(typeof value, "bigint");
}
function IsBoolean(value) {
  return IsEqual(typeof value, "boolean");
}
function IsConstructor(value) {
  if (IsUndefined(value) || !IsFunction(value))
    return false;
  const result = Function.prototype.toString.call(value);
  if (/^class\s/.test(result))
    return true;
  if (/\[native code\]/.test(result))
    return true;
  return false;
}
function IsFunction(value) {
  return IsEqual(typeof value, "function");
}
function IsInteger(value) {
  return Number.isInteger(value);
}
function IsNull(value) {
  return IsEqual(value, null);
}
function IsNumber(value) {
  return Number.isFinite(value);
}
function IsObjectNotArray(value) {
  return IsObject(value) && !IsArray(value);
}
function IsObject(value) {
  return IsEqual(typeof value, "object") && !IsNull(value);
}
function IsString(value) {
  return IsEqual(typeof value, "string");
}
function IsSymbol(value) {
  return IsEqual(typeof value, "symbol");
}
function IsUndefined(value) {
  return IsEqual(value, void 0);
}
function IsEqual(left, right) {
  return left === right;
}
function IsGreaterThan(left, right) {
  return left > right;
}
function IsLessThan(left, right) {
  return left < right;
}
function IsLessEqualThan(left, right) {
  return left <= right;
}
function IsGreaterEqualThan(left, right) {
  return left >= right;
}
function IsMultipleOf(dividend, divisor) {
  if (IsBigInt(dividend) || IsBigInt(divisor)) {
    return BigInt(dividend) % BigInt(divisor) === 0n;
  }
  const tolerance = 1e-10;
  if (!IsNumber(dividend))
    return true;
  if (IsInteger(dividend) && 1 / divisor % 1 === 0)
    return true;
  const mod = dividend % divisor;
  return Math.min(Math.abs(mod), Math.abs(mod - divisor), Math.abs(mod + divisor)) < tolerance;
}
function IsClassInstance(value) {
  if (!IsObject(value))
    return false;
  const proto = globalThis.Object.getPrototypeOf(value);
  if (IsNull(proto))
    return false;
  return IsEqual(typeof proto.constructor, "function") && !(IsEqual(proto.constructor, globalThis.Object) || IsEqual(proto.constructor.name, "Object"));
}
function IsValueLike(value) {
  return IsBigInt(value) || IsBoolean(value) || IsNull(value) || IsNumber(value) || IsString(value) || IsUndefined(value);
}
function GraphemeCount2(value) {
  return GraphemeCount(value);
}
function IsMaxLength2(value, length) {
  return IsMaxLengthFast(value, length);
}
function IsMinLength2(value, length) {
  return IsMinLengthFast(value, length);
}
function Every(value, offset, callback) {
  for (let index = offset; index < value.length; index++) {
    if (!callback(value[index], index))
      return false;
  }
  return true;
}
function EveryAll(value, offset, callback) {
  let result = true;
  for (let index = offset; index < value.length; index++) {
    if (!callback(value[index], index))
      result = false;
  }
  return result;
}
function ShiftLeft(array, true_, false_) {
  return IsEqual(array.length, 0) ? false_() : true_(array[0], array.slice(1));
}
function IsUnsafePropertyKey(key) {
  return IsEqual(key, "__proto__") || IsEqual(key, "constructor") || IsEqual(key, "prototype");
}
function HasPropertyKey(value, key) {
  return IsUnsafePropertyKey(key) ? Object.prototype.hasOwnProperty.call(value, key) : key in value;
}
function EntriesRegExp(value) {
  return Keys(value).map((key) => [new RegExp(`^${key}$`), value[key]]);
}
function Entries(value) {
  return Object.entries(value);
}
function Keys(value) {
  return Object.getOwnPropertyNames(value);
}
function Symbols(value) {
  return Object.getOwnPropertySymbols(value);
}
function Values(value) {
  return Object.values(value);
}
function DeepEqualObject(left, right) {
  if (!IsObject(right))
    return false;
  const keys = Keys(left);
  return IsEqual(keys.length, Keys(right).length) && keys.every((key) => IsDeepEqual(left[key], right[key]));
}
function DeepEqualArray(left, right) {
  return IsArray(right) && IsEqual(left.length, right.length) && left.every((_, index) => IsDeepEqual(left[index], right[index]));
}
function IsDeepEqual(left, right) {
  return IsArray(left) ? DeepEqualArray(left, right) : IsObject(left) ? DeepEqualObject(left, right) : IsEqual(left, right);
}

// node_modules/typebox/build/guard/globals.mjs
var globals_exports = {};
__export(globals_exports, {
  IsBigInt64Array: () => IsBigInt64Array,
  IsBigUint64Array: () => IsBigUint64Array,
  IsBoolean: () => IsBoolean2,
  IsDate: () => IsDate,
  IsFloat32Array: () => IsFloat32Array,
  IsFloat64Array: () => IsFloat64Array,
  IsInt16Array: () => IsInt16Array,
  IsInt32Array: () => IsInt32Array,
  IsInt8Array: () => IsInt8Array,
  IsMap: () => IsMap,
  IsNumber: () => IsNumber2,
  IsRegExp: () => IsRegExp,
  IsSet: () => IsSet,
  IsString: () => IsString2,
  IsTypeArray: () => IsTypeArray,
  IsUint16Array: () => IsUint16Array,
  IsUint32Array: () => IsUint32Array,
  IsUint8Array: () => IsUint8Array,
  IsUint8ClampedArray: () => IsUint8ClampedArray
});
function IsBoolean2(value) {
  return value instanceof Boolean;
}
function IsNumber2(value) {
  return value instanceof Number;
}
function IsString2(value) {
  return value instanceof String;
}
function IsTypeArray(value) {
  return globalThis.ArrayBuffer.isView(value);
}
function IsInt8Array(value) {
  return value instanceof globalThis.Int8Array;
}
function IsUint8Array(value) {
  return value instanceof globalThis.Uint8Array;
}
function IsUint8ClampedArray(value) {
  return value instanceof globalThis.Uint8ClampedArray;
}
function IsInt16Array(value) {
  return value instanceof globalThis.Int16Array;
}
function IsUint16Array(value) {
  return value instanceof globalThis.Uint16Array;
}
function IsInt32Array(value) {
  return value instanceof globalThis.Int32Array;
}
function IsUint32Array(value) {
  return value instanceof globalThis.Uint32Array;
}
function IsFloat32Array(value) {
  return value instanceof globalThis.Float32Array;
}
function IsFloat64Array(value) {
  return value instanceof globalThis.Float64Array;
}
function IsBigInt64Array(value) {
  return value instanceof globalThis.BigInt64Array;
}
function IsBigUint64Array(value) {
  return value instanceof globalThis.BigUint64Array;
}
function IsRegExp(value) {
  return value instanceof globalThis.RegExp;
}
function IsDate(value) {
  return value instanceof globalThis.Date;
}
function IsSet(value) {
  return value instanceof globalThis.Set;
}
function IsMap(value) {
  return value instanceof globalThis.Map;
}

// node_modules/typebox/build/system/memory/clone.mjs
function FromClassInstance(value) {
  return value;
}
function IsTypeObject(value) {
  return guard_exports.HasPropertyKey(value, "~kind") || guard_exports.HasPropertyKey(value, "~unsafe");
}
function FromTypeObject(value) {
  const result = {};
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of Object.keys(descriptors)) {
    if (guard_exports.IsUnsafePropertyKey(key))
      continue;
    const descriptor = descriptors[key];
    if (guard_exports.HasPropertyKey(descriptor, "value")) {
      Object.defineProperty(result, key, { ...descriptor, value: FromValue(descriptor.value) });
    }
  }
  return result;
}
function FromPlainObject(value) {
  const result = {};
  for (const key of guard_exports.Keys(value)) {
    if (guard_exports.IsUnsafePropertyKey(key))
      continue;
    result[key] = FromValue(value[key]);
  }
  for (const key of guard_exports.Symbols(value)) {
    result[key] = FromValue(value[key]);
  }
  return result;
}
function FromObject(value) {
  return guard_exports.IsClassInstance(value) ? FromClassInstance(value) : IsTypeObject(value) ? FromTypeObject(value) : FromPlainObject(value);
}
function FromArray(value) {
  return value.map((element) => FromValue(element));
}
function FromTypedArray(value) {
  return value.slice();
}
function FromRegExp(value) {
  return new RegExp(value.source, value.flags);
}
function FromMap(value) {
  return new Map(FromValue([...value.entries()]));
}
function FromSet(value) {
  return new Set(FromValue([...value.values()]));
}
function FromValue(value) {
  return globals_exports.IsTypeArray(value) ? FromTypedArray(value) : globals_exports.IsRegExp(value) ? FromRegExp(value) : globals_exports.IsMap(value) ? FromMap(value) : globals_exports.IsSet(value) ? FromSet(value) : guard_exports.IsArray(value) ? FromArray(value) : guard_exports.IsObject(value) ? FromObject(value) : value;
}
function Clone(value) {
  Metrics.clone += 1;
  return FromValue(value);
}

// node_modules/typebox/build/system/settings/settings.mjs
var settings_exports = {};
__export(settings_exports, {
  Get: () => Get,
  Reset: () => Reset,
  Set: () => Set2
});
var settings = {
  immutableTypes: false,
  maxErrors: 8,
  useAcceleration: true,
  exactOptionalPropertyTypes: false,
  enumerableKind: false,
  correctiveParse: false,
  unionPrioritySort: true
};
function Reset() {
  settings.immutableTypes = false;
  settings.maxErrors = 8;
  settings.useAcceleration = true;
  settings.exactOptionalPropertyTypes = false;
  settings.enumerableKind = false;
  settings.correctiveParse = false;
  settings.unionPrioritySort = true;
}
function Set2(options) {
  for (const key of guard_exports.Keys(options)) {
    const value = options[key];
    if (value !== void 0) {
      Object.defineProperty(settings, key, { value });
    }
  }
}
function Get() {
  return settings;
}

// node_modules/typebox/build/system/memory/create.mjs
function MergeHidden(left, right) {
  for (const key of Object.keys(right)) {
    Object.defineProperty(left, key, {
      configurable: true,
      writable: true,
      enumerable: false,
      value: right[key]
    });
  }
  return left;
}
function Merge(left, right) {
  return { ...left, ...right };
}
function Create(hidden, enumerable, options = {}) {
  Metrics.create += 1;
  const settings2 = settings_exports.Get();
  const withOptions = Merge(enumerable, options);
  const withHidden = settings2.enumerableKind ? Merge(withOptions, hidden) : MergeHidden(withOptions, hidden);
  return settings2.immutableTypes ? Object.freeze(withHidden) : withHidden;
}

// node_modules/typebox/build/system/memory/discard.mjs
function Discard(value, propertyKeys) {
  Metrics.discard += 1;
  const result = {};
  const descriptors = Object.getOwnPropertyDescriptors(Clone(value));
  const keysToDiscard = new Set(propertyKeys);
  for (const key of Object.keys(descriptors)) {
    if (keysToDiscard.has(key))
      continue;
    Object.defineProperty(result, key, descriptors[key]);
  }
  return result;
}

// node_modules/typebox/build/system/memory/update.mjs
function Update(current, hidden, enumerable) {
  Metrics.update += 1;
  const settings2 = settings_exports.Get();
  const result = Clone(current);
  for (const key of Object.keys(hidden)) {
    Object.defineProperty(result, key, {
      configurable: true,
      writable: true,
      enumerable: settings2.enumerableKind,
      value: hidden[key]
    });
  }
  for (const key of Object.keys(enumerable)) {
    Object.defineProperty(result, key, {
      configurable: true,
      enumerable: true,
      writable: true,
      value: enumerable[key]
    });
  }
  return result;
}

// node_modules/typebox/build/type/types/schema.mjs
function IsKind(value, kind) {
  return guard_exports.IsObject(value) && guard_exports.HasPropertyKey(value, "~kind") && guard_exports.IsEqual(value["~kind"], kind);
}
function IsSchema(value) {
  return guard_exports.IsObject(value);
}

// node_modules/typebox/build/type/types/deferred.mjs
function Deferred(action, parameters, options) {
  return memory_exports.Create({ "~kind": "Deferred" }, { type: "deferred", action, parameters, options }, {});
}
function IsDeferred(value) {
  return IsKind(value, "Deferred");
}

// node_modules/typebox/build/type/engine/readonly/instantiate_add.mjs
function AddReadonlyOperation(type) {
  return memory_exports.Update(type, { "~readonly": true }, {});
}
function AddReadonlyAction(type, options) {
  const result = memory_exports.Update(AddReadonlyOperation(type), {}, options);
  return result;
}
function AddReadonlyInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return AddReadonlyAction(instantiatedType, options);
}

// node_modules/typebox/build/type/engine/optional/instantiate_add.mjs
function AddOptionalOperation(type) {
  return memory_exports.Update(type, { "~optional": true }, {});
}
function AddOptionalAction(type, options) {
  const result = memory_exports.Update(AddOptionalOperation(type), {}, options);
  return result;
}
function AddOptionalInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return AddOptionalAction(instantiatedType, options);
}

// node_modules/typebox/build/type/types/array.mjs
function _Array_(items, options) {
  return memory_exports.Create({ "~kind": "Array" }, { type: "array", items }, options);
}
function IsArray2(value) {
  return IsKind(value, "Array");
}
function ArrayOptions(type) {
  return memory_exports.Discard(type, ["~kind", "type", "items"]);
}

// node_modules/typebox/build/type/types/constructor.mjs
function Constructor(parameters, instanceType, options = {}) {
  return memory_exports.Create({ "~kind": "Constructor" }, { type: "constructor", parameters, instanceType }, options);
}
function IsConstructor2(value) {
  return IsKind(value, "Constructor");
}
function ConstructorOptions(type) {
  return memory_exports.Discard(type, ["~kind", "type", "parameters", "instanceType"]);
}

// node_modules/typebox/build/type/types/function.mjs
function _Function_(parameters, returnType, options = {}) {
  return memory_exports.Create({ ["~kind"]: "Function" }, { type: "function", parameters, returnType }, options);
}
function IsFunction2(value) {
  return IsKind(value, "Function");
}
function FunctionOptions(type) {
  return memory_exports.Discard(type, ["~kind", "type", "parameters", "returnType"]);
}

// node_modules/typebox/build/type/types/ref.mjs
function Ref(ref, options) {
  return memory_exports.Create({ ["~kind"]: "Ref" }, { $ref: ref }, options);
}
function IsRef(value) {
  return IsKind(value, "Ref");
}

// node_modules/typebox/build/type/types/generic.mjs
function Generic(parameters, expression) {
  return memory_exports.Create({ "~kind": "Generic" }, { type: "generic", parameters, expression });
}
function IsGeneric(value) {
  return IsKind(value, "Generic");
}

// node_modules/typebox/build/type/types/any.mjs
function Any(options) {
  return memory_exports.Create({ ["~kind"]: "Any" }, {}, options);
}
function IsAny(value) {
  return IsKind(value, "Any");
}

// node_modules/typebox/build/type/types/never.mjs
var NeverPattern = "(?!)";
function Never(options) {
  return memory_exports.Create({ "~kind": "Never" }, { not: {} }, options);
}
function IsNever(value) {
  return IsKind(value, "Never");
}

// node_modules/typebox/build/type/action/_add_optional.mjs
function AddOptionalDeferred(type, options = {}) {
  return Deferred("AddOptional", [type], options);
}
function AddOptional(type, options = {}) {
  return AddOptionalAction(type, options);
}

// node_modules/typebox/build/type/types/_optional.mjs
function Optional(type) {
  return AddOptional(type);
}
function IsOptional(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "~optional");
}

// node_modules/typebox/build/type/types/properties.mjs
function RequiredArray(properties) {
  return guard_exports.Keys(properties).filter((key) => !IsOptional(properties[key]));
}
function PropertyKeys(properties) {
  return guard_exports.Keys(properties);
}
function PropertyValues(properties) {
  return guard_exports.Values(properties);
}

// node_modules/typebox/build/type/types/object.mjs
function _Object_(properties, options = {}) {
  const requiredKeys = RequiredArray(properties);
  const required = requiredKeys.length > 0 ? { required: requiredKeys } : {};
  return memory_exports.Create({ "~kind": "Object" }, { type: "object", ...required, properties }, options);
}
function IsObject2(value) {
  return IsKind(value, "Object");
}
function ObjectOptions(type) {
  return memory_exports.Discard(type, ["~kind", "type", "properties", "required"]);
}

// node_modules/typebox/build/type/types/unknown.mjs
function Unknown(options) {
  return memory_exports.Create({ ["~kind"]: "Unknown" }, {}, options);
}
function IsUnknown(value) {
  return IsKind(value, "Unknown");
}

// node_modules/typebox/build/type/types/cyclic.mjs
function Cyclic($defs, $ref, options) {
  const defs = guard_exports.Keys($defs).reduce((result, key) => {
    return { ...result, [key]: memory_exports.Update($defs[key], {}, { $id: key }) };
  }, {});
  return memory_exports.Create({ ["~kind"]: "Cyclic" }, { $defs: defs, $ref }, options);
}
function IsCyclic(value) {
  return IsKind(value, "Cyclic");
}

// node_modules/typebox/build/type/types/unsafe.mjs
function Unsafe(schema) {
  return memory_exports.Update(schema, { ["~unsafe"]: null }, {});
}
function IsUnsafe(value) {
  return guard_exports.IsObjectNotArray(value) && guard_exports.HasPropertyKey(value, "~unsafe") && guard_exports.IsNull(value["~unsafe"]);
}

// node_modules/typebox/build/system/arguments/arguments.mjs
var arguments_exports = {};
__export(arguments_exports, {
  Match: () => Match
});
function Match(args, match2) {
  return match2[args.length]?.(...args) ?? (() => {
    throw Error("Invalid Arguments");
  })();
}

// node_modules/typebox/build/type/types/infer.mjs
function Infer(...args) {
  const [name, extends_] = arguments_exports.Match(args, {
    2: (name2, extends_2) => [name2, extends_2, extends_2],
    1: (name2) => [name2, Unknown(), Unknown()]
  });
  return memory_exports.Create({ ["~kind"]: "Infer" }, { type: "infer", name, extends: extends_ }, {});
}
function IsInfer(value) {
  return IsKind(value, "Infer");
}

// node_modules/typebox/build/type/types/dependent.mjs
function Dependent(if_, then_, else_, options = {}) {
  return memory_exports.Create({ "~kind": "Dependent" }, { if: if_, then: then_, else: else_ }, options);
}
function IsDependent(value) {
  return IsKind(value, "Dependent");
}
function DependentOptions(type) {
  return memory_exports.Discard(type, ["~kind", "if", "then", "else"]);
}

// node_modules/typebox/build/type/engine/enum/typescript_enum_to_enum_values.mjs
function IsTypeScriptEnumLike(value) {
  return guard_exports.IsObjectNotArray(value);
}
function TypeScriptEnumToEnumValues(type) {
  const keys = guard_exports.Keys(type).filter((key) => isNaN(key));
  return keys.reduce((result, key) => [...result, type[key]], []);
}

// node_modules/typebox/build/type/types/enum.mjs
function IsEnumValue(value) {
  return guard_exports.IsString(value) || guard_exports.IsNumber(value);
}
function Enum(value, options) {
  const values = IsTypeScriptEnumLike(value) ? TypeScriptEnumToEnumValues(value) : value;
  return memory_exports.Create({ "~kind": "Enum" }, { enum: values }, options);
}
function IsEnum(value) {
  return IsKind(value, "Enum");
}

// node_modules/typebox/build/type/types/intersect.mjs
function Intersect(types2, options = {}) {
  return memory_exports.Create({ "~kind": "Intersect" }, { allOf: types2 }, options);
}
function IsIntersect(value) {
  return IsKind(value, "Intersect");
}
function IntersectOptions(type) {
  return memory_exports.Discard(type, ["~kind", "allOf"]);
}

// node_modules/typebox/build/system/unreachable/unreachable.mjs
function Unreachable() {
  throw new Error("Unreachable");
}

// node_modules/typebox/build/system/hashing/hash.mjs
var ByteMarker;
(function(ByteMarker2) {
  ByteMarker2[ByteMarker2["Array"] = 0] = "Array";
  ByteMarker2[ByteMarker2["BigInt"] = 1] = "BigInt";
  ByteMarker2[ByteMarker2["Boolean"] = 2] = "Boolean";
  ByteMarker2[ByteMarker2["Date"] = 3] = "Date";
  ByteMarker2[ByteMarker2["Constructor"] = 4] = "Constructor";
  ByteMarker2[ByteMarker2["Function"] = 5] = "Function";
  ByteMarker2[ByteMarker2["Null"] = 6] = "Null";
  ByteMarker2[ByteMarker2["Number"] = 7] = "Number";
  ByteMarker2[ByteMarker2["Object"] = 8] = "Object";
  ByteMarker2[ByteMarker2["RegExp"] = 9] = "RegExp";
  ByteMarker2[ByteMarker2["String"] = 10] = "String";
  ByteMarker2[ByteMarker2["Symbol"] = 11] = "Symbol";
  ByteMarker2[ByteMarker2["TypeArray"] = 12] = "TypeArray";
  ByteMarker2[ByteMarker2["Undefined"] = 13] = "Undefined";
})(ByteMarker || (ByteMarker = {}));
var Accumulator = BigInt("14695981039346656037");
var [Prime, Size] = [BigInt("1099511628211"), BigInt(
  "18446744073709551616"
  /* 2 ^ 64 */
)];
var Bytes = Array.from({ length: 256 }).map((_, i) => BigInt(i));
var F64 = new Float64Array(1);
var F64In = new DataView(F64.buffer);
var F64Out = new Uint8Array(F64.buffer);
var encoder = new TextEncoder();

// node_modules/typebox/build/type/types/_codec.mjs
var EncodeBuilder = class {
  constructor(type, decode) {
    this.type = type;
    this.decode = decode;
  }
  Encode(callback) {
    const type = this.type;
    const decode = IsCodec(type) ? (value) => this.decode(type["~codec"].decode(value)) : this.decode;
    const encode = IsCodec(type) ? (value) => type["~codec"].encode(callback(value)) : callback;
    const codec = { decode, encode };
    return memory_exports.Update(this.type, { "~codec": codec }, {});
  }
};
var DecodeBuilder = class {
  constructor(type) {
    this.type = type;
  }
  Decode(callback) {
    return new EncodeBuilder(this.type, callback);
  }
};
function Codec(type) {
  return new DecodeBuilder(type);
}
function Decode(type, callback) {
  return Codec(type).Decode(callback).Encode(() => {
    throw Error("Encode not implemented");
  });
}
function Encode(type, callback) {
  return Codec(type).Decode(() => {
    throw Error("Decode not implemented");
  }).Encode(callback);
}
function IsCodec(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "~codec") && guard_exports.IsObject(value["~codec"]) && guard_exports.HasPropertyKey(value["~codec"], "encode") && guard_exports.HasPropertyKey(value["~codec"], "decode");
}

// node_modules/typebox/build/type/types/_immutable.mjs
function Immutable(type) {
  return AddImmutable(type);
}
function IsImmutable(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "~immutable");
}

// node_modules/typebox/build/type/action/_add_readonly.mjs
function AddReadonlyDeferred(type, options = {}) {
  return Deferred("AddReadonly", [type], options);
}
function AddReadonly(type, options = {}) {
  return AddReadonlyAction(type, options);
}

// node_modules/typebox/build/type/types/_readonly.mjs
function Readonly(type) {
  return AddReadonly(type);
}
function IsReadonly(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "~readonly");
}

// node_modules/typebox/build/type/types/_refine.mjs
function RefineAdd(type, refinement) {
  const refinements = IsRefine(type) ? [...type["~refine"], refinement] : [refinement];
  return memory_exports.Update(type, { "~refine": refinements }, {});
}
function Refine(...args) {
  const [type, check, error] = arguments_exports.Match(args, {
    3: (type2, check2, error2) => [type2, check2, error2],
    2: (type2, check2) => [type2, check2, () => "Refine Error"]
  });
  return RefineAdd(type, { check, error });
}
function IsRefinement(value) {
  return guard_exports.IsObjectNotArray(value) && guard_exports.HasPropertyKey(value, "check") && guard_exports.HasPropertyKey(value, "error") && guard_exports.IsFunction(value.check) && guard_exports.IsFunction(value.error);
}
function IsRefine(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "~refine") && guard_exports.IsArray(value["~refine"]) && guard_exports.Every(value["~refine"], 0, (value2) => IsRefinement(value2));
}

// node_modules/typebox/build/type/types/bigint.mjs
var BigIntPattern = "-?(?:0|[1-9][0-9]*)n";
function BigInt2(options) {
  return memory_exports.Create({ "~kind": "BigInt" }, { type: "bigint" }, options);
}
function IsBigInt2(value) {
  return IsKind(value, "BigInt");
}

// node_modules/typebox/build/type/types/boolean.mjs
function Boolean2(options) {
  return memory_exports.Create({ "~kind": "Boolean" }, { type: "boolean" }, options);
}
function IsBoolean3(value) {
  return IsKind(value, "Boolean");
}

// node_modules/typebox/build/type/types/identifier.mjs
function Identifier(name) {
  return memory_exports.Create({ "~kind": "Identifier" }, { name });
}
function IsIdentifier(value) {
  return IsKind(value, "Identifier");
}

// node_modules/typebox/build/type/types/integer.mjs
var IntegerPattern = "-?(?:0|[1-9][0-9]*)";
function Integer(options) {
  return memory_exports.Create({ "~kind": "Integer" }, { type: "integer" }, options);
}
function IsInteger2(value) {
  return IsKind(value, "Integer");
}

// node_modules/typebox/build/type/types/literal.mjs
var InvalidLiteralValue = class extends Error {
  constructor(value) {
    super(`Invalid Literal value`);
    Object.defineProperty(this, "cause", {
      value: { value },
      writable: false,
      configurable: false,
      enumerable: false
    });
  }
};
function LiteralTypeName(value) {
  return guard_exports.IsBigInt(value) ? "bigint" : guard_exports.IsBoolean(value) ? "boolean" : guard_exports.IsNumber(value) ? "number" : guard_exports.IsString(value) ? "string" : (() => {
    throw new InvalidLiteralValue(value);
  })();
}
function Literal(value, options) {
  return memory_exports.Create({ "~kind": "Literal" }, { type: LiteralTypeName(value), const: value }, options);
}
function IsLiteralValue(value) {
  return guard_exports.IsBigInt(value) || guard_exports.IsBoolean(value) || guard_exports.IsNumber(value) || guard_exports.IsString(value);
}
function IsLiteralNumber(value) {
  return IsLiteral(value) && guard_exports.IsNumber(value.const);
}
function IsLiteralString(value) {
  return IsLiteral(value) && guard_exports.IsString(value.const);
}
function IsLiteral(value) {
  return IsKind(value, "Literal");
}

// node_modules/typebox/build/type/types/null.mjs
function Null(options) {
  return memory_exports.Create({ "~kind": "Null" }, { type: "null" }, options);
}
function IsNull2(value) {
  return IsKind(value, "Null");
}

// node_modules/typebox/build/type/types/number.mjs
var NumberPattern = "-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?";
function Number2(options) {
  return memory_exports.Create({ "~kind": "Number" }, { type: "number" }, options);
}
function IsNumber3(value) {
  return IsKind(value, "Number");
}

// node_modules/typebox/build/type/types/symbol.mjs
function Symbol2(options) {
  return memory_exports.Create({ "~kind": "Symbol" }, { type: "symbol" }, options);
}
function IsSymbol2(value) {
  return IsKind(value, "Symbol");
}

// node_modules/typebox/build/type/types/parameter.mjs
function Parameter(...args) {
  const [name, extends_, equals] = arguments_exports.Match(args, {
    3: (name2, extends_2, equals2) => [name2, extends_2, equals2],
    2: (name2, extends_2) => [name2, extends_2, extends_2],
    1: (name2) => [name2, Unknown(), Unknown()]
  });
  return memory_exports.Create({ "~kind": "Parameter" }, { name, extends: extends_, equals }, {});
}
function IsParameter(value) {
  return IsKind(value, "Parameter");
}

// node_modules/typebox/build/type/types/string.mjs
var StringPattern = ".*";
function String2(options) {
  return memory_exports.Create({ "~kind": "String" }, { type: "string" }, options);
}
function IsString3(value) {
  return IsKind(value, "String");
}

// node_modules/typebox/build/type/types/union.mjs
function Union(anyOf, options = {}) {
  return memory_exports.Create({ "~kind": "Union" }, { anyOf }, options);
}
function IsUnion(value) {
  return IsKind(value, "Union");
}
function UnionOptions(type) {
  return memory_exports.Discard(type, ["~kind", "anyOf"]);
}

// node_modules/typebox/build/type/engine/patterns/pattern.mjs
function ParsePatternIntoTypes(pattern) {
  const parsed = Pattern(pattern);
  const result = guard_exports.IsEqual(parsed.length, 2) ? parsed[0] : [];
  return result;
}

// node_modules/typebox/build/type/engine/template_literal/is_finite.mjs
function FromLiteral(_value) {
  return true;
}
function FromTypesReduce(types2) {
  return guard_exports.ShiftLeft(types2, (left, right) => FromType(left) ? FromTypesReduce(right) : false, () => true);
}
function FromTypes(types2) {
  const result = guard_exports.IsEqual(types2.length, 0) ? false : FromTypesReduce(types2);
  return result;
}
function FromType(type) {
  return IsUnion(type) ? FromTypes(type.anyOf) : IsLiteral(type) ? FromLiteral(type.const) : false;
}
function IsTemplateLiteralFinite(types2) {
  const result = FromTypes(types2);
  return result;
}

// node_modules/typebox/build/type/engine/template_literal/create.mjs
function TemplateLiteralCreate(pattern) {
  return memory_exports.Create({ ["~kind"]: "TemplateLiteral" }, { type: "string", pattern }, {});
}

// node_modules/typebox/build/type/engine/template_literal/decode.mjs
function FromLiteralPush(variants, value, result = []) {
  return guard_exports.ShiftLeft(variants, (left, right) => FromLiteralPush(right, value, [...result, `${left}${value}`]), () => result);
}
function FromLiteral2(variants, value) {
  return guard_exports.IsEqual(variants.length, 0) ? [`${value}`] : FromLiteralPush(variants, value);
}
function FromUnion(variants, types2, result = []) {
  return guard_exports.ShiftLeft(types2, (left, right) => FromUnion(variants, right, [...result, ...FromType2(variants, left)]), () => result);
}
function FromType2(variants, type) {
  const result = IsUnion(type) ? FromUnion(variants, type.anyOf) : IsLiteral(type) ? FromLiteral2(variants, type.const) : Unreachable();
  return result;
}
function DecodeFromSpan(variants, types2) {
  return guard_exports.ShiftLeft(types2, (left, right) => DecodeFromSpan(FromType2(variants, left), right), () => variants);
}
function VariantsToLiterals(variants) {
  return variants.map((variant) => Literal(variant));
}
function DecodeTypesAsUnion(types2) {
  const variants = DecodeFromSpan([], types2);
  const literals = VariantsToLiterals(variants);
  const result = Union(literals);
  return result;
}
function DecodeTypes(types2) {
  return guard_exports.IsEqual(types2.length, 0) ? Unreachable() : (
    // Literal('') :
    guard_exports.IsEqual(types2.length, 1) && IsLiteral(types2[0]) ? types2[0] : DecodeTypesAsUnion(types2)
  );
}
function TemplateLiteralDecodeUnsafe(pattern) {
  const types2 = ParsePatternIntoTypes(pattern);
  const result = guard_exports.IsEqual(types2.length, 0) ? String2() : IsTemplateLiteralFinite(types2) ? DecodeTypes(types2) : TemplateLiteralCreate(pattern);
  return result;
}
function TemplateLiteralDecode(pattern) {
  const decoded = TemplateLiteralDecodeUnsafe(pattern);
  const result = IsTemplateLiteral(decoded) ? String2() : decoded;
  return result;
}

// node_modules/typebox/build/type/engine/record/record_create.mjs
function CreateRecord(key, value) {
  const type = "object";
  const patternProperties = { [key]: value };
  return memory_exports.Create({ ["~kind"]: "Record" }, { type, patternProperties });
}

// node_modules/typebox/build/type/engine/record/from_key_any.mjs
function FromAnyKey(value) {
  return CreateRecord(StringKey, value);
}

// node_modules/typebox/build/type/engine/record/from_key_boolean.mjs
function FromBooleanKey(value) {
  return _Object_({ true: value, false: value });
}

// node_modules/typebox/build/type/types/tuple.mjs
function Tuple(types2, options = {}) {
  const [items, minItems, additionalItems] = [types2, types2.length, false];
  return memory_exports.Create({ ["~kind"]: "Tuple" }, { type: "array", additionalItems, items, minItems }, options);
}
function IsTuple(value) {
  return IsKind(value, "Tuple");
}
function TupleOptions(type) {
  return memory_exports.Discard(type, ["~kind", "type", "items", "minItems", "additionalItems"]);
}

// node_modules/typebox/build/type/engine/readonly/instantiate_remove.mjs
function RemoveReadonlyOperation(type) {
  return memory_exports.Discard(type, ["~readonly"]);
}
function RemoveReadonlyAction(type, options) {
  const result = memory_exports.Update(RemoveReadonlyOperation(type), {}, options);
  return result;
}
function RemoveReadonlyInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return RemoveReadonlyAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/_remove_readonly.mjs
function RemoveReadonlyDeferred(type, options = {}) {
  return Deferred("RemoveReadonly", [type], options);
}
function RemoveReadonly(type, options = {}) {
  return RemoveReadonlyAction(type, options);
}

// node_modules/typebox/build/type/engine/optional/instantiate_remove.mjs
function RemoveOptionalOperation(type) {
  return memory_exports.Discard(type, ["~optional"]);
}
function RemoveOptionalAction(type, options) {
  const result = memory_exports.Update(RemoveOptionalOperation(type), {}, options);
  return result;
}
function RemoveOptionalInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return RemoveOptionalAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/_remove_optional.mjs
function RemoveOptionalDeferred(type, options = {}) {
  return Deferred("RemoveOptional", [type], options);
}
function RemoveOptional(type, options = {}) {
  return RemoveOptionalAction(type, options);
}

// node_modules/typebox/build/type/engine/tuple/to_object.mjs
function TupleElementsToProperties(types2) {
  const result = types2.reduceRight((result2, right, index) => {
    return { [index]: right, ...result2 };
  }, {});
  return result;
}
function TupleToObject(type) {
  const properties = TupleElementsToProperties(type.items);
  const result = _Object_(properties);
  return result;
}

// node_modules/typebox/build/type/engine/evaluate/composite.mjs
function IsReadonlyProperty(left, right) {
  return IsReadonly(left) ? IsReadonly(right) ? true : false : false;
}
function IsOptionalProperty(left, right) {
  return IsOptional(left) ? IsOptional(right) ? true : false : false;
}
function CompositeProperty(left, right) {
  const isReadonly = IsReadonlyProperty(left, right);
  const isOptional = IsOptionalProperty(left, right);
  const evaluated = EvaluateIntersect([left, right]);
  const property = RemoveReadonly(RemoveOptional(evaluated));
  return isReadonly && isOptional ? AddReadonly(AddOptional(property)) : isReadonly && !isOptional ? AddReadonly(property) : !isReadonly && isOptional ? AddOptional(property) : property;
}
function CompositePropertyKey(left, right, key) {
  return key in left ? key in right ? CompositeProperty(left[key], right[key]) : left[key] : key in right ? right[key] : Never();
}
function CompositeProperties(left, right) {
  const keys = /* @__PURE__ */ new Set([...guard_exports.Keys(right), ...guard_exports.Keys(left)]);
  return [...keys].reduce((result, key) => {
    return { ...result, [key]: CompositePropertyKey(left, right, key) };
  }, {});
}
function GetProperties(type) {
  const result = IsObject2(type) ? type.properties : IsTuple(type) ? TupleElementsToProperties(type.items) : Unreachable();
  return result;
}
function Composite(left, right) {
  const leftProperties = GetProperties(left);
  const rightProperties = GetProperties(right);
  const properties = CompositeProperties(leftProperties, rightProperties);
  return _Object_(properties);
}

// node_modules/typebox/build/type/engine/evaluate/narrow.mjs
function Narrow(left, right) {
  const result = Compare(left, right);
  return guard_exports.IsEqual(result, ResultLeftInside) ? left : guard_exports.IsEqual(result, ResultRightInside) ? right : guard_exports.IsEqual(result, ResultEqual) ? right : Never();
}

// node_modules/typebox/build/type/engine/evaluate/distribute.mjs
function IsObjectLike(type) {
  return IsObject2(type) || IsTuple(type);
}
function IsUnionOperand(left, right) {
  const isUnionLeft = IsUnion(left);
  const isUnionRight = IsUnion(right);
  const result = isUnionLeft || isUnionRight;
  return result;
}
function DistributeOperation(left, right) {
  const evaluatedLeft = EvaluateType(left);
  const evaluatedRight = EvaluateType(right);
  const isUnionOperand = IsUnionOperand(evaluatedLeft, evaluatedRight);
  const isObjectLeft = IsObjectLike(evaluatedLeft);
  const IsObjectRight = IsObjectLike(evaluatedRight);
  const result = isUnionOperand ? EvaluateIntersect([evaluatedLeft, evaluatedRight]) : isObjectLeft && IsObjectRight ? Composite(evaluatedLeft, evaluatedRight) : isObjectLeft && !IsObjectRight ? evaluatedLeft : !isObjectLeft && IsObjectRight ? evaluatedRight : Narrow(evaluatedLeft, evaluatedRight);
  return result;
}
function DistributeType(type, types2, result = []) {
  return guard_exports.ShiftLeft(types2, (left, right) => DistributeType(type, right, [...result, DistributeOperation(type, left)]), () => guard_exports.IsEqual(result.length, 0) ? [type] : result);
}
function DistributeUnion(types2, distribution, result = []) {
  return guard_exports.ShiftLeft(types2, (left, right) => DistributeUnion(right, distribution, [...result, ...Distribute([left], distribution)]), () => result);
}
function Distribute(types2, result = []) {
  return guard_exports.ShiftLeft(types2, (left, right) => IsUnion(left) ? Distribute(right, DistributeUnion(left.anyOf, result)) : Distribute(right, DistributeType(left, result)), () => result);
}

// node_modules/typebox/build/type/engine/exclude/operation.mjs
function ExcludeType(left, right) {
  const check = Extends({}, left, right);
  const result = result_exports.IsExtendsTrueLike(check) ? [] : [left];
  return result;
}
function ExcludeUnion(types2, right) {
  return types2.reduce((result, head) => {
    return [...result, ...ExcludeType(head, right)];
  }, []);
}
function ExcludeOperation(left, right) {
  const evaluated = EvaluateType(left);
  const canonical = IsUnion(evaluated) ? evaluated.anyOf : [evaluated];
  const remaining = ExcludeUnion(canonical, right);
  const result = EvaluateUnion(remaining);
  return result;
}

// node_modules/typebox/build/type/engine/evaluate/evaluate.mjs
function EvaluateDependent(if_, then_, else_) {
  const intersect = Intersect([if_, then_]);
  const excluded = ExcludeOperation(else_, if_);
  const result = EvaluateUnion([intersect, excluded]);
  return result;
}
function EvaluateEnum(values) {
  const result = values.map((value) => Literal(value));
  return EvaluateUnion(result);
}
function EvaluateIntersect(types2) {
  const distribution = Distribute(types2);
  const broadend = Broaden(distribution);
  const result = EvaluateUnionFast(broadend);
  return result;
}
function EvaluateTemplateLiteral(pattern) {
  const evaluated = TemplateLiteralDecode(pattern);
  const result = EvaluateType(evaluated);
  return result;
}
function EvaluateUnion(types2) {
  const broadend = Broaden(types2);
  const result = EvaluateUnionFast(broadend);
  return result;
}
function EvaluateType(type) {
  return IsDependent(type) ? EvaluateDependent(type.if, type.then, type.else) : IsEnum(type) ? EvaluateEnum(type.enum) : IsIntersect(type) ? EvaluateIntersect(type.allOf) : IsTemplateLiteral(type) ? EvaluateTemplateLiteral(type.pattern) : IsUnion(type) ? EvaluateUnion(type.anyOf) : type;
}
function EvaluateUnionFast(types2) {
  const result = guard_exports.IsEqual(types2.length, 1) ? types2[0] : guard_exports.IsEqual(types2.length, 0) ? Never() : Union(types2);
  return result;
}

// node_modules/typebox/build/type/engine/record/from_key_enum.mjs
function FromEnumKey(values, value) {
  const unionKey = EvaluateEnum(values);
  const result = FromKey(unionKey, value);
  return result;
}

// node_modules/typebox/build/type/engine/record/from_key_integer.mjs
function FromIntegerKey(_key, value) {
  const result = CreateRecord(IntegerKey, value);
  return result;
}

// node_modules/typebox/build/type/engine/record/from_key_intersect.mjs
function FromIntersectKey(types2, value) {
  const evaluatedKey = EvaluateIntersect(types2);
  const result = FromKey(evaluatedKey, value);
  return result;
}

// node_modules/typebox/build/type/engine/record/from_key_literal.mjs
function FromLiteralKey(key, value) {
  return guard_exports.IsString(key) || guard_exports.IsNumber(key) ? _Object_({ [key]: value }) : guard_exports.IsEqual(key, false) ? _Object_({ false: value }) : guard_exports.IsEqual(key, true) ? _Object_({ true: value }) : _Object_({});
}

// node_modules/typebox/build/type/engine/record/from_key_number.mjs
function FromNumberKey(_key, value) {
  const result = CreateRecord(NumberKey, value);
  return result;
}

// node_modules/typebox/build/type/engine/record/from_key_string.mjs
function FromStringKey(key, value) {
  return guard_exports.HasPropertyKey(key, "pattern") && (guard_exports.IsString(key.pattern) || key.pattern instanceof RegExp) ? CreateRecord(key.pattern.toString(), value) : CreateRecord(StringKey, value);
}

// node_modules/typebox/build/type/engine/record/from_key_template_literal.mjs
function FromTemplateKey(pattern, value) {
  const types2 = ParsePatternIntoTypes(pattern);
  const finite = IsTemplateLiteralFinite(types2);
  const result = finite ? FromKey(EvaluateTemplateLiteral(pattern), value) : CreateRecord(pattern, value);
  return result;
}

// node_modules/typebox/build/type/engine/evaluate/flatten.mjs
function FlattenType(type) {
  const result = IsUnion(type) ? Flatten(type.anyOf) : [type];
  return result;
}
function Flatten(types2) {
  return types2.reduce((result, type) => {
    return [...result, ...FlattenType(type)];
  }, []);
}

// node_modules/typebox/build/type/engine/record/from_key_union.mjs
function StringOrNumberCheck(types2) {
  return types2.some((type) => IsString3(type) || IsNumber3(type) || IsInteger2(type));
}
function TryBuildRecord(types2, value) {
  return guard_exports.IsEqual(StringOrNumberCheck(types2), true) ? CreateRecord(StringKey, value) : void 0;
}
function CreateProperties(types2, value) {
  return types2.reduce((result, left) => {
    return IsLiteral(left) && (guard_exports.IsString(left.const) || guard_exports.IsNumber(left.const)) ? { ...result, [left.const]: value } : result;
  }, {});
}
function CreateObject(types2, value) {
  const properties = CreateProperties(types2, value);
  const result = _Object_(properties);
  return result;
}
function FromUnionKey(types2, value) {
  const flattened = Flatten(types2);
  const record = TryBuildRecord(flattened, value);
  return IsSchema(record) ? record : CreateObject(flattened, value);
}

// node_modules/typebox/build/type/engine/record/from_key.mjs
function FromKey(key, value) {
  const result = IsAny(key) ? FromAnyKey(value) : IsBoolean3(key) ? FromBooleanKey(value) : IsEnum(key) ? FromEnumKey(key.enum, value) : IsInteger2(key) ? FromIntegerKey(key, value) : IsIntersect(key) ? FromIntersectKey(key.allOf, value) : IsLiteral(key) ? FromLiteralKey(key.const, value) : IsNumber3(key) ? FromNumberKey(key, value) : IsUnion(key) ? FromUnionKey(key.anyOf, value) : IsString3(key) ? FromStringKey(key, value) : IsTemplateLiteral(key) ? FromTemplateKey(key.pattern, value) : _Object_({});
  return result;
}

// node_modules/typebox/build/type/engine/record/instantiate.mjs
function RecordAction(key, value, options) {
  const result = CanInstantiate([key]) ? memory_exports.Update(FromKey(key, value), {}, options) : RecordDeferred(key, value, options);
  return result;
}
function RecordInstantiate(context, state, key, value, options) {
  const instantiatedKey = InstantiateType(context, state, key);
  const instantiatedValue = InstantiateType(context, state, value);
  return RecordAction(instantiatedKey, instantiatedValue, options);
}

// node_modules/typebox/build/type/types/record.mjs
var IntegerKey = `^${IntegerPattern}$`;
var NumberKey = `^${NumberPattern}$`;
var StringKey = `^${StringPattern}$`;
function RecordDeferred(key, value, options = {}) {
  return Deferred("Record", [key, value], options);
}
function Record(key, value, options = {}) {
  return RecordAction(key, value, options);
}
function RecordFromPattern(pattern, value) {
  return CreateRecord(pattern, value);
}
function RecordPatternToType(pattern) {
  const result = guard_exports.IsEqual(pattern, StringKey) ? String2() : guard_exports.IsEqual(pattern, IntegerKey) ? Integer() : guard_exports.IsEqual(pattern, NumberKey) ? Number2() : TemplateLiteralDecodeUnsafe(pattern);
  return result;
}
function RecordPattern(type) {
  return guard_exports.Keys(type.patternProperties)[0];
}
function RecordKey(type) {
  const pattern = RecordPattern(type);
  const result = RecordPatternToType(pattern);
  return result;
}
function RecordValue(type) {
  return type.patternProperties[RecordPattern(type)];
}
function IsRecord(value) {
  return IsKind(value, "Record");
}

// node_modules/typebox/build/type/types/rest.mjs
function Rest(type) {
  return memory_exports.Create({ "~kind": "Rest" }, { type: "rest", items: type }, {});
}
function IsRest(value) {
  return IsKind(value, "Rest");
}

// node_modules/typebox/build/type/types/this.mjs
function This(options) {
  return memory_exports.Create({ ["~kind"]: "This" }, { $ref: "#" }, options);
}
function IsThis(value) {
  return IsKind(value, "This");
}

// node_modules/typebox/build/type/types/undefined.mjs
function Undefined(options) {
  return memory_exports.Create({ "~kind": "Undefined" }, { type: "undefined" }, options);
}
function IsUndefined2(value) {
  return IsKind(value, "Undefined");
}

// node_modules/typebox/build/type/types/void.mjs
function Void(options) {
  return memory_exports.Create({ "~kind": "Void" }, { type: "void" }, options);
}
function IsVoid(value) {
  return IsKind(value, "Void");
}

// node_modules/typebox/build/type/script/mapping.mjs
function IntrinsicOrCall(ref, parameters) {
  return guard_exports.IsEqual(ref, "Array") ? _Array_(parameters[0]) : guard_exports.IsEqual(ref, "Capitalize") ? CapitalizeDeferred(parameters[0]) : guard_exports.IsEqual(ref, "ConstructorParameters") ? ConstructorParametersDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Evaluate") ? EvaluateDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Exclude") ? ExcludeDeferred(parameters[0], parameters[1]) : guard_exports.IsEqual(ref, "Extract") ? ExtractDeferred(parameters[0], parameters[1]) : guard_exports.IsEqual(ref, "Index") ? IndexDeferred(parameters[0], parameters[1]) : guard_exports.IsEqual(ref, "InstanceType") ? InstanceTypeDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Lowercase") ? LowercaseDeferred(parameters[0]) : guard_exports.IsEqual(ref, "NonNullable") ? NonNullableDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Omit") ? OmitDeferred(parameters[0], parameters[1]) : guard_exports.IsEqual(ref, "Parameters") ? ParametersDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Partial") ? PartialDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Pick") ? PickDeferred(parameters[0], parameters[1]) : guard_exports.IsEqual(ref, "Readonly") ? ReadonlyObjectDeferred(parameters[0]) : guard_exports.IsEqual(ref, "KeyOf") ? KeyOfDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Record") ? RecordDeferred(parameters[0], parameters[1]) : guard_exports.IsEqual(ref, "Required") ? RequiredDeferred(parameters[0]) : guard_exports.IsEqual(ref, "ReturnType") ? ReturnTypeDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Uncapitalize") ? UncapitalizeDeferred(parameters[0]) : guard_exports.IsEqual(ref, "Uppercase") ? UppercaseDeferred(parameters[0]) : CallConstruct(Ref(ref), parameters);
}
function Unreachable2() {
  throw Error("Unreachable");
}
var DelimitedDecode = (input, result = []) => {
  return input.reduce((result2, left) => {
    return guard_exports.IsArray(left) && guard_exports.IsEqual(left.length, 2) ? [...result2, left[0]] : [...result2, left];
  }, []);
};
var Delimited = (input) => {
  const [left, right] = input;
  return DelimitedDecode([...left, ...right]);
};
function GenericParameterExtendsEqualsMapping(input) {
  return Parameter(input[0], input[2], input[4]);
}
function GenericParameterExtendsMapping(input) {
  return Parameter(input[0], input[2], input[2]);
}
function GenericParameterEqualsMapping(input) {
  return Parameter(input[0], Unknown(), input[2]);
}
function GenericParameterIdentifierMapping(input) {
  return Parameter(input, Unknown(), Unknown());
}
function GenericParameterMapping(input) {
  return input;
}
function GenericParameterListMapping(input) {
  return Delimited(input);
}
function GenericParametersMapping(input) {
  return input[1];
}
function GenericCallArgumentListMapping(input) {
  return Delimited(input);
}
function GenericCallArgumentsMapping(input) {
  return input[1];
}
function GenericCallMapping(input) {
  return IntrinsicOrCall(input[0], input[1]);
}
function OptionalSemiColonMapping(input) {
  return null;
}
function KeywordStringMapping(input) {
  return String2();
}
function KeywordNumberMapping(input) {
  return Number2();
}
function KeywordBooleanMapping(input) {
  return Boolean2();
}
function KeywordUndefinedMapping(input) {
  return Undefined();
}
function KeywordNullMapping(input) {
  return Null();
}
function KeywordIntegerMapping(input) {
  return Integer();
}
function KeywordBigIntMapping(input) {
  return BigInt2();
}
function KeywordUnknownMapping(input) {
  return Unknown();
}
function KeywordAnyMapping(input) {
  return Any();
}
function KeywordObjectMapping(input) {
  return _Object_({});
}
function KeywordNeverMapping(input) {
  return Never();
}
function KeywordSymbolMapping(input) {
  return Symbol2();
}
function KeywordVoidMapping(input) {
  return Void();
}
function KeywordThisMapping(input) {
  return This();
}
function LiteralBigIntMapping(input) {
  return Literal(BigInt(input));
}
function LiteralBooleanMapping(input) {
  return Literal(guard_exports.IsEqual(input, "true"));
}
function LiteralNumberMapping(input) {
  return Literal(parseFloat(input));
}
function LiteralStringMapping(input) {
  return Literal(input);
}
function TemplateInterpolateMapping(input) {
  return input[1];
}
function TemplateSpanMapping(input) {
  return Literal(input);
}
function TemplateBodyMapping(input) {
  return guard_exports.IsEqual(input.length, 3) ? [input[0], input[1], ...input[2]] : [input[0]];
}
function TemplateLiteralTypesMapping(input) {
  return input[1];
}
function TemplateLiteralMapping(input) {
  return TemplateLiteralDeferred(input);
}
function DependentMapping(input) {
  return guard_exports.IsEqual(input.length, 6) ? Dependent(input[1], input[3], input[5]) : Dependent(input[1], input[3], Unknown());
}
function KeyOfMapping(input) {
  return input.length > 0;
}
function IndexArrayMapping(input) {
  return input.reduce((result, current) => {
    return guard_exports.IsEqual(current.length, 3) ? [...result, [current[1]]] : [...result, []];
  }, []);
}
function ExtendsMapping(input) {
  return guard_exports.IsEqual(input.length, 6) ? [input[1], input[3], input[5]] : [];
}
function BaseMapping(input) {
  return guard_exports.IsArray(input) && guard_exports.IsEqual(input.length, 3) ? input[1] : input;
}
function WithMapping(input) {
  return guard_exports.IsEqual(input.length, 2) ? input[1] : [];
}
function FactorIndexArray(Type2, indexArray) {
  return indexArray.reduce((result, left) => {
    const _left = left;
    return guard_exports.IsEqual(_left.length, 1) ? IndexDeferred(result, _left[0]) : guard_exports.IsEqual(_left.length, 0) ? _Array_(result) : Unreachable2();
  }, Type2);
}
function FactorExtends(type, extend) {
  return guard_exports.IsEqual(extend.length, 3) ? ConditionalDeferred(type, extend[0], extend[1], extend[2]) : type;
}
function FactorWith(type, withClause) {
  return guard_exports.IsArray(withClause) && guard_exports.IsEqual(withClause.length, 0) ? type : WithDeferred(type, withClause);
}
function FactorMapping(input) {
  const [keyOf, type, indexArray, extend, withClause] = input;
  return FactorWith(keyOf ? FactorExtends(KeyOfDeferred(FactorIndexArray(type, indexArray)), extend) : FactorExtends(FactorIndexArray(type, indexArray), extend), withClause);
}
function ExprBinaryMapping(left, rest) {
  return guard_exports.IsEqual(rest.length, 3) ? (() => {
    const [operator, right, next] = rest;
    const Schema = ExprBinaryMapping(right, next);
    if (guard_exports.IsEqual(operator, "&")) {
      return IsIntersect(Schema) ? Intersect([left, ...Schema.allOf]) : Intersect([left, Schema]);
    }
    if (guard_exports.IsEqual(operator, "|")) {
      return IsUnion(Schema) ? Union([left, ...Schema.anyOf]) : Union([left, Schema]);
    }
    Unreachable2();
  })() : left;
}
function ExprTermTailMapping(input) {
  return input;
}
function ExprTermMapping(input) {
  const [left, rest] = input;
  return ExprBinaryMapping(left, rest);
}
function ExprTailMapping(input) {
  return input;
}
function ExprMapping(input) {
  const [left, rest] = input;
  return ExprBinaryMapping(left, rest);
}
function ExprReadonlyMapping(input) {
  return AddImmutableDeferred(input[1]);
}
function ExprPipeMapping(input) {
  return input[1];
}
function GenericTypeMapping(input) {
  return Generic(input[0], input[2]);
}
function InferTypeMapping(input) {
  return guard_exports.IsEqual(input.length, 4) ? Infer(input[1], input[3]) : guard_exports.IsEqual(input.length, 2) ? Infer(input[1], Unknown()) : Unreachable2();
}
function TypeMapping(input) {
  return input;
}
function PropertyKeyNumberMapping(input) {
  return `${input}`;
}
function PropertyKeyIdentMapping(input) {
  return input;
}
function PropertyKeyQuotedMapping(input) {
  return input;
}
function PropertyKeyIndexMapping(input) {
  return IsInteger2(input[3]) ? IntegerKey : IsNumber3(input[3]) ? NumberKey : IsSymbol2(input[3]) ? StringKey : IsString3(input[3]) ? StringKey : Unreachable2();
}
function PropertyKeyMapping(input) {
  return input;
}
function ReadonlyMapping(input) {
  return input.length > 0;
}
function OptionalMapping(input) {
  return input.length > 0;
}
function PropertyMapping(input) {
  const [isReadonly, key, isOptional, _colon, type] = input;
  return {
    [key]: isReadonly && isOptional ? AddReadonlyDeferred(AddOptionalDeferred(type)) : isReadonly && !isOptional ? AddReadonlyDeferred(type) : !isReadonly && isOptional ? AddOptionalDeferred(type) : type
  };
}
function PropertyDelimiterMapping(input) {
  return input;
}
function PropertyListMapping(input) {
  return Delimited(input);
}
function PropertiesReduce(propertyList) {
  return propertyList.reduce((result, left) => {
    const isPatternProperties = guard_exports.HasPropertyKey(left, IntegerKey) || guard_exports.HasPropertyKey(left, NumberKey) || guard_exports.HasPropertyKey(left, StringKey);
    return isPatternProperties ? [result[0], memory_exports.Assign(result[1], left)] : [memory_exports.Assign(result[0], left), result[1]];
  }, [{}, {}]);
}
function PropertiesMapping(input) {
  return PropertiesReduce(input[1]);
}
function _Object_Mapping(input) {
  const [properties, patternProperties] = input;
  const options = guard_exports.IsEqual(guard_exports.Keys(patternProperties).length, 0) ? {} : { patternProperties };
  return _Object_(properties, options);
}
function ElementNamedMapping(input) {
  return guard_exports.IsEqual(input.length, 5) ? AddReadonlyDeferred(AddOptionalDeferred(input[4])) : guard_exports.IsEqual(input.length, 3) ? input[2] : guard_exports.IsEqual(input.length, 4) ? guard_exports.IsEqual(input[2], "readonly") ? AddReadonlyDeferred(input[3]) : AddOptionalDeferred(input[3]) : Unreachable2();
}
function ElementReadonlyOptionalMapping(input) {
  return AddReadonlyDeferred(AddOptionalDeferred(input[1]));
}
function ElementReadonlyMapping(input) {
  return AddReadonlyDeferred(input[1]);
}
function ElementOptionalMapping(input) {
  return AddOptionalDeferred(input[0]);
}
function ElementBaseMapping(input) {
  return input;
}
function ElementMapping(input) {
  return guard_exports.IsEqual(input.length, 2) ? Rest(input[1]) : guard_exports.IsEqual(input.length, 1) ? input[0] : Unreachable2();
}
function ElementListMapping(input) {
  return Delimited(input);
}
function _Tuple_Mapping(input) {
  return Tuple(input[1]);
}
function ParameterReadonlyOptionalMapping(input) {
  return AddReadonlyDeferred(AddOptionalDeferred(input[4]));
}
function ParameterReadonlyMapping(input) {
  return AddReadonlyDeferred(input[3]);
}
function ParameterOptionalMapping(input) {
  return AddOptionalDeferred(input[3]);
}
function ParameterTypeMapping(input) {
  return input[2];
}
function ParameterBaseMapping(input) {
  return input;
}
function ParameterMapping(input) {
  return guard_exports.IsEqual(input.length, 2) ? Rest(input[1]) : guard_exports.IsEqual(input.length, 1) ? input[0] : Unreachable2();
}
function ParameterListMapping(input) {
  return Delimited(input);
}
function _Function_Mapping(input) {
  return _Function_(input[1], input[4]);
}
function _Constructor_Mapping(input) {
  return Constructor(input[2], input[5]);
}
function ApplyReadonly(state, type) {
  return guard_exports.IsEqual(state, "remove") ? RemoveReadonlyDeferred(type) : guard_exports.IsEqual(state, "add") ? AddReadonlyDeferred(type) : type;
}
function MappedReadonlyMapping(input) {
  return guard_exports.IsEqual(input.length, 2) && guard_exports.IsEqual(input[0], "-") ? "remove" : guard_exports.IsEqual(input.length, 2) && guard_exports.IsEqual(input[0], "+") ? "add" : guard_exports.IsEqual(input.length, 1) ? "add" : "none";
}
function ApplyOptional(state, type) {
  return guard_exports.IsEqual(state, "remove") ? RemoveOptionalDeferred(type) : guard_exports.IsEqual(state, "add") ? AddOptionalDeferred(type) : type;
}
function MappedOptionalMapping(input) {
  return guard_exports.IsEqual(input.length, 2) && guard_exports.IsEqual(input[0], "-") ? "remove" : guard_exports.IsEqual(input.length, 2) && guard_exports.IsEqual(input[0], "+") ? "add" : guard_exports.IsEqual(input.length, 1) ? "add" : "none";
}
function MappedAsMapping(input) {
  return guard_exports.IsEqual(input.length, 2) ? [input[1]] : [];
}
function _Mapped_Mapping(input) {
  return guard_exports.IsArray(input[6]) && guard_exports.IsEqual(input[6].length, 1) ? MappedDeferred(Identifier(input[3]), input[5], input[6][0], ApplyReadonly(input[1], ApplyOptional(input[8], input[10]))) : MappedDeferred(Identifier(input[3]), input[5], Ref(input[3]), ApplyReadonly(input[1], ApplyOptional(input[8], input[10])));
}
function ReferenceMapping(input) {
  return Ref(input);
}
function WithBigIntMapping(input) {
  return BigInt(input);
}
function WithNumberMapping(input) {
  return parseFloat(input);
}
function WithBooleanMapping(input) {
  return guard_exports.IsEqual(input, "true");
}
function WithStringMapping(input) {
  return input;
}
function WithNullMapping(input) {
  return null;
}
function WithUndefinedMapping(input) {
  return void 0;
}
function WithPropertyMapping(input) {
  return { [input[0]]: input[2] };
}
function WithPropertyListMapping(input) {
  return Delimited(input);
}
function WithObjectMappingReduce(propertyList) {
  return propertyList.reduce((result, left) => {
    return memory_exports.Assign(result, left);
  }, {});
}
function WithObjectMapping(input) {
  return WithObjectMappingReduce(input[1]);
}
function WithElementListMapping(input) {
  return Delimited(input);
}
function WithArrayMapping(input) {
  return input[1];
}
function WithValueMapping(input) {
  return input;
}
function PatternBigIntMapping(input) {
  return BigInt2();
}
function PatternStringMapping(input) {
  return String2();
}
function PatternNumberMapping(input) {
  return Number2();
}
function PatternIntegerMapping(input) {
  return Integer();
}
function PatternNeverMapping(input) {
  return Never();
}
function PatternTextMapping(input) {
  return Literal(input);
}
function PatternBaseMapping(input) {
  return input;
}
function PatternGroupMapping(input) {
  return Union(input[1]);
}
function PatternUnionMapping(input) {
  return input.length === 3 ? [...input[0], ...input[2]] : input.length === 1 ? [...input[0]] : [];
}
function PatternTermMapping(input) {
  return [input[0], ...input[1]];
}
function PatternBodyMapping(input) {
  return input;
}
function PatternMapping(input) {
  return input[1];
}
function InterfaceDeclarationHeritageListMapping(input) {
  return Delimited(input);
}
function InterfaceDeclarationHeritageMapping(input) {
  return guard_exports.IsEqual(input.length, 2) ? input[1] : [];
}
function InterfaceDeclarationGenericMapping(input) {
  const parameters = input[2];
  const heritage = input[3];
  const [properties, patternProperties] = input[4];
  const options = guard_exports.IsEqual(guard_exports.Keys(patternProperties).length, 0) ? {} : { patternProperties };
  return { [input[1]]: Generic(parameters, InterfaceDeferred(heritage, properties, options)) };
}
function InterfaceDeclarationMapping(input) {
  const heritage = input[2];
  const [properties, patternProperties] = input[3];
  const options = guard_exports.IsEqual(guard_exports.Keys(patternProperties).length, 0) ? {} : { patternProperties };
  return { [input[1]]: InterfaceDeferred(heritage, properties, options) };
}
function TypeAliasDeclarationGenericMapping(input) {
  return { [input[1]]: Generic(input[2], input[4]) };
}
function TypeAliasDeclarationMapping(input) {
  return { [input[1]]: input[3] };
}
function ExportKeywordMapping(input) {
  return null;
}
function ModuleDeclarationDelimiterMapping(input) {
  return input;
}
function ModuleDeclarationListMapping(input) {
  return PropertiesReduce(Delimited(input));
}
function ModuleDeclarationMapping(input) {
  return input[1];
}
function ModuleMapping(input) {
  const moduleDeclaration = input[0];
  const moduleDeclarationList = input[1];
  return ModuleDeferred(memory_exports.Assign(moduleDeclaration, moduleDeclarationList[0]));
}
function ScriptMapping(input) {
  return input;
}

// node_modules/typebox/build/type/script/token/internal/match.mjs
function IsMatch(value) {
  return IsEqual(value.length, 2);
}
function Match2(input, ok, fail4) {
  return IsMatch(input) ? ok(input[0], input[1]) : fail4();
}

// node_modules/typebox/build/type/script/token/internal/take.mjs
function TakeVariant(variant, input) {
  return IsEqual(input.indexOf(variant), 0) ? [variant, input.slice(variant.length)] : [];
}
function Take(variants, input) {
  for (let i = 0; i < variants.length; i++) {
    const result = TakeVariant(variants[i], input);
    if (IsMatch(result))
      return result;
  }
  return [];
}

// node_modules/typebox/build/type/script/token/internal/char.mjs
function Range(start, end) {
  return Array.from({ length: end - start + 1 }, (_, i) => String.fromCharCode(start + i));
}
var Alpha = [
  ...Range(97, 122),
  // Lowercase
  ...Range(65, 90)
  // Uppercase
];
var Zero = "0";
var NonZero = Range(49, 57);
var Digit = [Zero, ...NonZero];
var WhiteSpace = " ";
var NewLine = "\n";
var UnderScore = "_";
var Dot = ".";
var DollarSign = "$";
var Hyphen = "-";

// node_modules/typebox/build/type/script/token/internal/trim.mjs
var LineComment = "//";
var OpenComment = "/*";
var CloseComment = "*/";
function DiscardMultilineComment(input) {
  const index = input.indexOf(CloseComment);
  const result = IsEqual(index, -1) ? "" : input.slice(index + 2);
  return result;
}
function DiscardLineComment(input) {
  const index = input.indexOf(NewLine);
  const result = IsEqual(index, -1) ? "" : input.slice(index);
  return result;
}
function TrimStartUntilNewline(input) {
  return input.replace(/^[ \t\r\f\v]+/, "");
}
function TrimWhitespace(input) {
  const trimmed = TrimStartUntilNewline(input);
  return trimmed.startsWith(OpenComment) ? TrimWhitespace(DiscardMultilineComment(trimmed.slice(2))) : trimmed.startsWith(LineComment) ? TrimWhitespace(DiscardLineComment(trimmed.slice(2))) : trimmed;
}
function Trim(input) {
  const trimmed = input.trimStart();
  return trimmed.startsWith(OpenComment) ? Trim(DiscardMultilineComment(trimmed.slice(2))) : trimmed.startsWith(LineComment) ? Trim(DiscardLineComment(trimmed.slice(2))) : trimmed;
}

// node_modules/typebox/build/type/script/token/internal/optional.mjs
function Optional2(value, input) {
  return Match2(Take([value], input), (Optional4, Rest2) => [Optional4, Rest2], () => ["", input]);
}

// node_modules/typebox/build/type/script/token/internal/many.mjs
function IsDiscard(discard, input) {
  return discard.includes(input);
}
function Many(allowed, discard, input, result = "") {
  return Match2(Take(allowed, input), (Char, Rest2) => IsDiscard(discard, Char) ? Many(allowed, discard, Rest2, result) : Many(allowed, discard, Rest2, `${result}${Char}`), () => [result, input]);
}

// node_modules/typebox/build/type/script/token/unsigned_integer.mjs
function TakeNonZero(input) {
  return Take(NonZero, input);
}
var AllowedDigits = [...Digit, UnderScore];
function TakeDigits(input) {
  return Many(AllowedDigits, [UnderScore], input);
}
function TakeUnsignedInteger(input) {
  return Match2(Take([Zero], input), (Zero2, ZeroRest) => [Zero2, ZeroRest], () => Match2(
    TakeNonZero(input),
    (NonZero2, NonZeroRest) => Match2(TakeDigits(NonZeroRest), (Digits, DigitsRest) => [`${NonZero2}${Digits}`, DigitsRest], () => []),
    // fail: did not match Digits
    () => []
  ));
}
function UnsignedInteger(input) {
  return TakeUnsignedInteger(Trim(input));
}

// node_modules/typebox/build/type/script/token/integer.mjs
function TakeSign(input) {
  return Optional2(Hyphen, input);
}
function TakeSignedInteger(input) {
  return Match2(
    TakeSign(input),
    (Sign, SignRest) => Match2(UnsignedInteger(SignRest), (UnsignedInteger2, UnsignedIntegerRest) => [`${Sign}${UnsignedInteger2}`, UnsignedIntegerRest], () => []),
    // fail: did not match unsigned integer
    () => []
  );
}
function Integer2(input) {
  return TakeSignedInteger(Trim(input));
}

// node_modules/typebox/build/type/script/token/bigint.mjs
function TakeBigInt(input) {
  return Match2(
    Integer2(input),
    (Integer3, IntegerRest) => Match2(Take(["n"], IntegerRest), (_N, NRest) => [`${Integer3}`, NRest], () => []),
    // fail: did not match 'n'
    () => []
  );
}
function BigInt3(input) {
  return TakeBigInt(input);
}

// node_modules/typebox/build/type/script/token/const.mjs
function TakeConst(const_, input) {
  return Take([const_], input);
}
function Const(const_, input) {
  return IsEqual(const_, "") ? ["", input] : const_.startsWith(NewLine) ? TakeConst(const_, TrimWhitespace(input)) : const_.startsWith(WhiteSpace) ? TakeConst(const_, input) : TakeConst(const_, Trim(input));
}

// node_modules/typebox/build/type/script/token/ident.mjs
var Initial = [...Alpha, UnderScore, DollarSign];
function TakeInitial(input) {
  return Take(Initial, input);
}
var Remaining = [...Initial, ...Digit];
function TakeRemaining(input, result = "") {
  return Match2(Take(Remaining, input), (Remaining2, RemainingRest) => TakeRemaining(RemainingRest, `${result}${Remaining2}`), () => [result, input]);
}
function TakeIdent(input) {
  return Match2(
    TakeInitial(input),
    (Initial2, InitialRest) => Match2(TakeRemaining(InitialRest), (Remaining2, RemainingRest) => [`${Initial2}${Remaining2}`, RemainingRest], () => []),
    // fail: did not match Remaining
    () => []
  );
}
function Ident(input) {
  return TakeIdent(Trim(input));
}

// node_modules/typebox/build/type/script/token/unsigned_number.mjs
var AllowedDigits2 = [...Digit, UnderScore];
function IsLeadingDot(input) {
  return IsMatch(Take([Dot], input));
}
function TakeFractional(input) {
  return Match2(Many(AllowedDigits2, [UnderScore], input), (Digits, DigitsRest) => IsEqual(Digits, "") ? [] : [Digits, DigitsRest], () => []);
}
function LeadingDot(input) {
  return Match2(
    Take([Dot], input),
    (Dot2, DotRest) => Match2(TakeFractional(DotRest), (Fractional, FractionalRest) => [`0${Dot2}${Fractional}`, FractionalRest], () => []),
    // fail: did not match Fractional
    () => []
  );
}
function LeadingInteger(input) {
  return Match2(
    UnsignedInteger(input),
    (Integer3, IntegerRest) => Match2(
      Take([Dot], IntegerRest),
      (Dot2, DotRest) => Match2(TakeFractional(DotRest), (Fractional, FractionalRest) => [`${Integer3}${Dot2}${Fractional}`, FractionalRest], () => [`${Integer3}`, DotRest]),
      // fail: did not match Fractional, use Integer
      () => [`${Integer3}`, IntegerRest]
    ),
    // fail: did not match Dot, use Integer
    () => []
  );
}
function TakeUnsignedNumber(input) {
  return IsLeadingDot(input) ? LeadingDot(input) : LeadingInteger(input);
}
function UnsignedNumber(input) {
  return TakeUnsignedNumber(Trim(input));
}

// node_modules/typebox/build/type/script/token/number.mjs
function TakeSign2(input) {
  return Optional2(Hyphen, input);
}
function TakeSignedNumber(input) {
  return Match2(
    TakeSign2(input),
    (Sign, SignRest) => Match2(UnsignedNumber(SignRest), (UnsignedInteger2, UnsignedIntegerRest) => [`${Sign}${UnsignedInteger2}`, UnsignedIntegerRest], () => []),
    // fail: did not match unsigned integer
    () => []
  );
}
function Number3(input) {
  return TakeSignedNumber(Trim(input));
}

// node_modules/typebox/build/type/script/token/until.mjs
function TakeOne(input) {
  const result = IsEqual(input, "") ? [] : [input.slice(0, 1), input.slice(1)];
  return result;
}
function IsInputMatchSentinal(end, input) {
  return ShiftLeft(end, (left, right) => input.startsWith(left) ? true : IsInputMatchSentinal(right, input), () => false);
}
function Until(end, input, result = "") {
  return Match2(
    TakeOne(input),
    (One, Rest2) => IsInputMatchSentinal(end, input) ? [result, input] : Until(end, Rest2, `${result}${One}`),
    () => []
  );
}

// node_modules/typebox/build/type/script/token/span.mjs
function MultiLine(start, end, input) {
  return Match2(
    Take([start], input),
    (_, Rest2) => Match2(
      Until([end], Rest2),
      (Until2, UntilRest) => Match2(Take([end], UntilRest), (_2, Rest3) => [`${Until2}`, Rest3], () => []),
      // fail: did not match End
      () => []
    ),
    // fail: did not match Until
    () => []
  );
}
function SingleLine(start, end, input) {
  return Match2(
    Take([start], input),
    (_, Rest2) => Match2(
      Until([NewLine, end], Rest2),
      (Until2, UntilRest) => Match2(Take([end], UntilRest), (_2, EndRest) => [`${Until2}`, EndRest], () => []),
      // fail: did not match End
      () => []
    ),
    // fail: did not match Until
    () => []
  );
}
function Span(start, end, multiLine, input) {
  return multiLine ? MultiLine(start, end, Trim(input)) : SingleLine(start, end, Trim(input));
}

// node_modules/typebox/build/type/script/token/string.mjs
function TakeInitial2(quotes, input) {
  return Take(quotes, input);
}
function TakeSpan(quote, input) {
  return Span(quote, quote, false, input);
}
function TakeString(quotes, input) {
  return Match2(TakeInitial2(quotes, input), (Initial2, InitialRest) => TakeSpan(Initial2, `${Initial2}${InitialRest}`), () => []);
}
function String3(quotes, input) {
  return TakeString(quotes, Trim(input));
}

// node_modules/typebox/build/type/script/token/until_1.mjs
function Until_1(end, input) {
  return Match2(Until(end, input), (Until2, UntilRest) => IsEqual(Until2, "") ? [] : [Until2, UntilRest], () => []);
}

// node_modules/typebox/build/type/script/parser.mjs
var If = (result, left, right = () => []) => result.length === 2 ? left(result) : right();
var GenericParameterExtendsEquals = (input) => If(If(Ident(input), ([_0, input2]) => If(Const("extends", input2), ([_1, input3]) => If(Type(input3), ([_2, input4]) => If(Const("=", input4), ([_3, input5]) => If(Type(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [GenericParameterExtendsEqualsMapping(_0), input2]);
var GenericParameterExtends = (input) => If(If(Ident(input), ([_0, input2]) => If(Const("extends", input2), ([_1, input3]) => If(Type(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [GenericParameterExtendsMapping(_0), input2]);
var GenericParameterEquals = (input) => If(If(Ident(input), ([_0, input2]) => If(Const("=", input2), ([_1, input3]) => If(Type(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [GenericParameterEqualsMapping(_0), input2]);
var GenericParameterIdentifier = (input) => If(Ident(input), ([_0, input2]) => [GenericParameterIdentifierMapping(_0), input2]);
var GenericParameter = (input) => If(If(GenericParameterExtendsEquals(input), ([_0, input2]) => [_0, input2], () => If(GenericParameterExtends(input), ([_0, input2]) => [_0, input2], () => If(GenericParameterEquals(input), ([_0, input2]) => [_0, input2], () => If(GenericParameterIdentifier(input), ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [GenericParameterMapping(_0), input2]);
var GenericParameterList_0 = (input, result = []) => If(If(GenericParameter(input), ([_0, input2]) => If(Const(",", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => GenericParameterList_0(input2, [...result, _0]), () => [result, input]);
var GenericParameterList = (input) => If(If(GenericParameterList_0(input), ([_0, input2]) => If(If(If(GenericParameter(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [GenericParameterListMapping(_0), input2]);
var GenericParameters = (input) => If(If(Const("<", input), ([_0, input2]) => If(GenericParameterList(input2), ([_1, input3]) => If(Const(">", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [GenericParametersMapping(_0), input2]);
var GenericCallArgumentList_0 = (input, result = []) => If(If(Type(input), ([_0, input2]) => If(Const(",", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => GenericCallArgumentList_0(input2, [...result, _0]), () => [result, input]);
var GenericCallArgumentList = (input) => If(If(GenericCallArgumentList_0(input), ([_0, input2]) => If(If(If(Type(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [GenericCallArgumentListMapping(_0), input2]);
var GenericCallArguments = (input) => If(If(Const("<", input), ([_0, input2]) => If(GenericCallArgumentList(input2), ([_1, input3]) => If(Const(">", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [GenericCallArgumentsMapping(_0), input2]);
var GenericCall = (input) => If(If(Ident(input), ([_0, input2]) => If(GenericCallArguments(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [GenericCallMapping(_0), input2]);
var OptionalSemiColon = (input) => If(If(If(Const(";", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [OptionalSemiColonMapping(_0), input2]);
var KeywordString = (input) => If(Const("string", input), ([_0, input2]) => [KeywordStringMapping(_0), input2]);
var KeywordNumber = (input) => If(Const("number", input), ([_0, input2]) => [KeywordNumberMapping(_0), input2]);
var KeywordBoolean = (input) => If(Const("boolean", input), ([_0, input2]) => [KeywordBooleanMapping(_0), input2]);
var KeywordUndefined = (input) => If(Const("undefined", input), ([_0, input2]) => [KeywordUndefinedMapping(_0), input2]);
var KeywordNull = (input) => If(Const("null", input), ([_0, input2]) => [KeywordNullMapping(_0), input2]);
var KeywordInteger = (input) => If(Const("integer", input), ([_0, input2]) => [KeywordIntegerMapping(_0), input2]);
var KeywordBigInt = (input) => If(Const("bigint", input), ([_0, input2]) => [KeywordBigIntMapping(_0), input2]);
var KeywordUnknown = (input) => If(Const("unknown", input), ([_0, input2]) => [KeywordUnknownMapping(_0), input2]);
var KeywordAny = (input) => If(Const("any", input), ([_0, input2]) => [KeywordAnyMapping(_0), input2]);
var KeywordObject = (input) => If(Const("object", input), ([_0, input2]) => [KeywordObjectMapping(_0), input2]);
var KeywordNever = (input) => If(Const("never", input), ([_0, input2]) => [KeywordNeverMapping(_0), input2]);
var KeywordSymbol = (input) => If(Const("symbol", input), ([_0, input2]) => [KeywordSymbolMapping(_0), input2]);
var KeywordVoid = (input) => If(Const("void", input), ([_0, input2]) => [KeywordVoidMapping(_0), input2]);
var KeywordThis = (input) => If(Const("this", input), ([_0, input2]) => [KeywordThisMapping(_0), input2]);
var TemplateInterpolate = (input) => If(If(Const("${", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const("}", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [TemplateInterpolateMapping(_0), input2]);
var TemplateSpan = (input) => If(Until(["${", "`"], input), ([_0, input2]) => [TemplateSpanMapping(_0), input2]);
var TemplateBody = (input) => If(If(If(TemplateSpan(input), ([_0, input2]) => If(TemplateInterpolate(input2), ([_1, input3]) => If(TemplateBody(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => If(If(TemplateSpan(input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If(If(TemplateSpan(input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => []))), ([_0, input2]) => [TemplateBodyMapping(_0), input2]);
var TemplateLiteralTypes = (input) => If(If(Const("`", input), ([_0, input2]) => If(TemplateBody(input2), ([_1, input3]) => If(Const("`", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [TemplateLiteralTypesMapping(_0), input2]);
var TemplateLiteral = (input) => If(TemplateLiteralTypes(input), ([_0, input2]) => [TemplateLiteralMapping(_0), input2]);
var Dependent2 = (input) => If(If(If(Const("if", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const("then", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => If(Const("else", input5), ([_4, input6]) => If(Type(input6), ([_5, input7]) => [[_0, _1, _2, _3, _4, _5], input7])))))), ([_0, input2]) => [_0, input2], () => If(If(Const("if", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const("then", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [DependentMapping(_0), input2]);
var LiteralBigInt = (input) => If(BigInt3(input), ([_0, input2]) => [LiteralBigIntMapping(_0), input2]);
var LiteralBoolean = (input) => If(If(Const("true", input), ([_0, input2]) => [_0, input2], () => If(Const("false", input), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [LiteralBooleanMapping(_0), input2]);
var LiteralNumber = (input) => If(Number3(input), ([_0, input2]) => [LiteralNumberMapping(_0), input2]);
var LiteralString = (input) => If(String3(["'", '"'], input), ([_0, input2]) => [LiteralStringMapping(_0), input2]);
var KeyOf = (input) => If(If(If(Const("keyof", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [KeyOfMapping(_0), input2]);
var IndexArray_0 = (input, result = []) => If(If(If(Const("[", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const("]", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => If(If(Const("[", input), ([_0, input2]) => If(Const("]", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => IndexArray_0(input2, [...result, _0]), () => [result, input]);
var IndexArray = (input) => If(IndexArray_0(input), ([_0, input2]) => [IndexArrayMapping(_0), input2]);
var Extends2 = (input) => If(If(If(Const("extends", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const("?", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => If(Const(":", input5), ([_4, input6]) => If(Type(input6), ([_5, input7]) => [[_0, _1, _2, _3, _4, _5], input7])))))), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ExtendsMapping(_0), input2]);
var Base = (input) => If(If(If(Const("(", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const(")", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => If(KeywordString(input), ([_0, input2]) => [_0, input2], () => If(KeywordNumber(input), ([_0, input2]) => [_0, input2], () => If(KeywordBoolean(input), ([_0, input2]) => [_0, input2], () => If(KeywordUndefined(input), ([_0, input2]) => [_0, input2], () => If(KeywordNull(input), ([_0, input2]) => [_0, input2], () => If(KeywordInteger(input), ([_0, input2]) => [_0, input2], () => If(KeywordBigInt(input), ([_0, input2]) => [_0, input2], () => If(KeywordUnknown(input), ([_0, input2]) => [_0, input2], () => If(KeywordAny(input), ([_0, input2]) => [_0, input2], () => If(KeywordObject(input), ([_0, input2]) => [_0, input2], () => If(KeywordNever(input), ([_0, input2]) => [_0, input2], () => If(KeywordSymbol(input), ([_0, input2]) => [_0, input2], () => If(KeywordVoid(input), ([_0, input2]) => [_0, input2], () => If(KeywordThis(input), ([_0, input2]) => [_0, input2], () => If(LiteralBigInt(input), ([_0, input2]) => [_0, input2], () => If(LiteralBoolean(input), ([_0, input2]) => [_0, input2], () => If(LiteralNumber(input), ([_0, input2]) => [_0, input2], () => If(LiteralString(input), ([_0, input2]) => [_0, input2], () => If(TemplateLiteral(input), ([_0, input2]) => [_0, input2], () => If(Dependent2(input), ([_0, input2]) => [_0, input2], () => If(_Object_2(input), ([_0, input2]) => [_0, input2], () => If(_Tuple_(input), ([_0, input2]) => [_0, input2], () => If(_Constructor_(input), ([_0, input2]) => [_0, input2], () => If(_Function_2(input), ([_0, input2]) => [_0, input2], () => If(_Mapped_(input), ([_0, input2]) => [_0, input2], () => If(GenericCall(input), ([_0, input2]) => [_0, input2], () => If(Reference(input), ([_0, input2]) => [_0, input2], () => [])))))))))))))))))))))))))))), ([_0, input2]) => [BaseMapping(_0), input2]);
var With = (input) => If(If(If(Const("with", input), ([_0, input2]) => If(WithObject(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [WithMapping(_0), input2]);
var Factor = (input) => If(If(KeyOf(input), ([_0, input2]) => If(Base(input2), ([_1, input3]) => If(IndexArray(input3), ([_2, input4]) => If(Extends2(input4), ([_3, input5]) => If(With(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [FactorMapping(_0), input2]);
var ExprTermTail = (input) => If(If(If(Const("&", input), ([_0, input2]) => If(Factor(input2), ([_1, input3]) => If(ExprTermTail(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ExprTermTailMapping(_0), input2]);
var ExprTerm = (input) => If(If(Factor(input), ([_0, input2]) => If(ExprTermTail(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ExprTermMapping(_0), input2]);
var ExprTail = (input) => If(If(If(Const("|", input), ([_0, input2]) => If(ExprTerm(input2), ([_1, input3]) => If(ExprTail(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ExprTailMapping(_0), input2]);
var Expr = (input) => If(If(ExprTerm(input), ([_0, input2]) => If(ExprTail(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ExprMapping(_0), input2]);
var ExprReadonly = (input) => If(If(Const("readonly", input), ([_0, input2]) => If(Expr(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ExprReadonlyMapping(_0), input2]);
var ExprPipe = (input) => If(If(Const("|", input), ([_0, input2]) => If(Expr(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ExprPipeMapping(_0), input2]);
var GenericType = (input) => If(If(GenericParameters(input), ([_0, input2]) => If(Const("=", input2), ([_1, input3]) => If(Type(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [GenericTypeMapping(_0), input2]);
var InferType = (input) => If(If(If(Const("infer", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => If(Const("extends", input3), ([_2, input4]) => If(Expr(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [_0, input2], () => If(If(Const("infer", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [InferTypeMapping(_0), input2]);
var Type = (input) => If(If(InferType(input), ([_0, input2]) => [_0, input2], () => If(ExprPipe(input), ([_0, input2]) => [_0, input2], () => If(ExprReadonly(input), ([_0, input2]) => [_0, input2], () => If(Expr(input), ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [TypeMapping(_0), input2]);
var PropertyKeyNumber = (input) => If(Number3(input), ([_0, input2]) => [PropertyKeyNumberMapping(_0), input2]);
var PropertyKeyIdent = (input) => If(Ident(input), ([_0, input2]) => [PropertyKeyIdentMapping(_0), input2]);
var PropertyKeyQuoted = (input) => If(String3(["'", '"'], input), ([_0, input2]) => [PropertyKeyQuotedMapping(_0), input2]);
var PropertyKeyIndex = (input) => If(If(Const("[", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => If(Const(":", input3), ([_2, input4]) => If(If(KeywordInteger(input4), ([_02, input5]) => [_02, input5], () => If(KeywordNumber(input4), ([_02, input5]) => [_02, input5], () => If(KeywordString(input4), ([_02, input5]) => [_02, input5], () => If(KeywordSymbol(input4), ([_02, input5]) => [_02, input5], () => [])))), ([_3, input5]) => If(Const("]", input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [PropertyKeyIndexMapping(_0), input2]);
var PropertyKey = (input) => If(If(PropertyKeyNumber(input), ([_0, input2]) => [_0, input2], () => If(PropertyKeyIdent(input), ([_0, input2]) => [_0, input2], () => If(PropertyKeyQuoted(input), ([_0, input2]) => [_0, input2], () => If(PropertyKeyIndex(input), ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [PropertyKeyMapping(_0), input2]);
var Readonly2 = (input) => If(If(If(Const("readonly", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ReadonlyMapping(_0), input2]);
var Optional3 = (input) => If(If(If(Const("?", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [OptionalMapping(_0), input2]);
var Property = (input) => If(If(Readonly2(input), ([_0, input2]) => If(PropertyKey(input2), ([_1, input3]) => If(Optional3(input3), ([_2, input4]) => If(Const(":", input4), ([_3, input5]) => If(Type(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [PropertyMapping(_0), input2]);
var PropertyDelimiter = (input) => If(If(If(Const(",", input), ([_0, input2]) => If(Const("\n", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const(";", input), ([_0, input2]) => If(Const("\n", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const(",", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If(If(Const(";", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If(If(Const("\n", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => []))))), ([_0, input2]) => [PropertyDelimiterMapping(_0), input2]);
var PropertyList_0 = (input, result = []) => If(If(Property(input), ([_0, input2]) => If(PropertyDelimiter(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => PropertyList_0(input2, [...result, _0]), () => [result, input]);
var PropertyList = (input) => If(If(PropertyList_0(input), ([_0, input2]) => If(If(If(Property(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [PropertyListMapping(_0), input2]);
var Properties = (input) => If(If(Const("{", input), ([_0, input2]) => If(PropertyList(input2), ([_1, input3]) => If(Const("}", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [PropertiesMapping(_0), input2]);
var _Object_2 = (input) => If(Properties(input), ([_0, input2]) => [_Object_Mapping(_0), input2]);
var ElementNamed = (input) => If(If(If(Ident(input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => If(Const(":", input3), ([_2, input4]) => If(Const("readonly", input4), ([_3, input5]) => If(Type(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [_0, input2], () => If(If(Ident(input), ([_0, input2]) => If(Const(":", input2), ([_1, input3]) => If(Const("readonly", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [_0, input2], () => If(If(Ident(input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => If(Const(":", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [_0, input2], () => If(If(Ident(input), ([_0, input2]) => If(Const(":", input2), ([_1, input3]) => If(Type(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [ElementNamedMapping(_0), input2]);
var ElementReadonlyOptional = (input) => If(If(Const("readonly", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => If(Const("?", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [ElementReadonlyOptionalMapping(_0), input2]);
var ElementReadonly = (input) => If(If(Const("readonly", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ElementReadonlyMapping(_0), input2]);
var ElementOptional = (input) => If(If(Type(input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ElementOptionalMapping(_0), input2]);
var ElementBase = (input) => If(If(ElementNamed(input), ([_0, input2]) => [_0, input2], () => If(ElementReadonlyOptional(input), ([_0, input2]) => [_0, input2], () => If(ElementReadonly(input), ([_0, input2]) => [_0, input2], () => If(ElementOptional(input), ([_0, input2]) => [_0, input2], () => If(Type(input), ([_0, input2]) => [_0, input2], () => []))))), ([_0, input2]) => [ElementBaseMapping(_0), input2]);
var Element = (input) => If(If(If(Const("...", input), ([_0, input2]) => If(ElementBase(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(ElementBase(input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ElementMapping(_0), input2]);
var ElementList_0 = (input, result = []) => If(If(Element(input), ([_0, input2]) => If(Const(",", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => ElementList_0(input2, [...result, _0]), () => [result, input]);
var ElementList = (input) => If(If(ElementList_0(input), ([_0, input2]) => If(If(If(Element(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ElementListMapping(_0), input2]);
var _Tuple_ = (input) => If(If(Const("[", input), ([_0, input2]) => If(ElementList(input2), ([_1, input3]) => If(Const("]", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_Tuple_Mapping(_0), input2]);
var ParameterReadonlyOptional = (input) => If(If(Ident(input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => If(Const(":", input3), ([_2, input4]) => If(Const("readonly", input4), ([_3, input5]) => If(Type(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [ParameterReadonlyOptionalMapping(_0), input2]);
var ParameterReadonly = (input) => If(If(Ident(input), ([_0, input2]) => If(Const(":", input2), ([_1, input3]) => If(Const("readonly", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [ParameterReadonlyMapping(_0), input2]);
var ParameterOptional = (input) => If(If(Ident(input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => If(Const(":", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [ParameterOptionalMapping(_0), input2]);
var ParameterType = (input) => If(If(Ident(input), ([_0, input2]) => If(Const(":", input2), ([_1, input3]) => If(Type(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [ParameterTypeMapping(_0), input2]);
var ParameterBase = (input) => If(If(ParameterReadonlyOptional(input), ([_0, input2]) => [_0, input2], () => If(ParameterReadonly(input), ([_0, input2]) => [_0, input2], () => If(ParameterOptional(input), ([_0, input2]) => [_0, input2], () => If(ParameterType(input), ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [ParameterBaseMapping(_0), input2]);
var Parameter2 = (input) => If(If(If(Const("...", input), ([_0, input2]) => If(ParameterBase(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(ParameterBase(input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ParameterMapping(_0), input2]);
var ParameterList_0 = (input, result = []) => If(If(Parameter2(input), ([_0, input2]) => If(Const(",", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => ParameterList_0(input2, [...result, _0]), () => [result, input]);
var ParameterList = (input) => If(If(ParameterList_0(input), ([_0, input2]) => If(If(If(Parameter2(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ParameterListMapping(_0), input2]);
var _Function_2 = (input) => If(If(Const("(", input), ([_0, input2]) => If(ParameterList(input2), ([_1, input3]) => If(Const(")", input3), ([_2, input4]) => If(Const("=>", input4), ([_3, input5]) => If(Type(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [_Function_Mapping(_0), input2]);
var _Constructor_ = (input) => If(If(Const("new", input), ([_0, input2]) => If(Const("(", input2), ([_1, input3]) => If(ParameterList(input3), ([_2, input4]) => If(Const(")", input4), ([_3, input5]) => If(Const("=>", input5), ([_4, input6]) => If(Type(input6), ([_5, input7]) => [[_0, _1, _2, _3, _4, _5], input7])))))), ([_0, input2]) => [_Constructor_Mapping(_0), input2]);
var MappedReadonly = (input) => If(If(If(Const("+", input), ([_0, input2]) => If(Const("readonly", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const("-", input), ([_0, input2]) => If(Const("readonly", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const("readonly", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [MappedReadonlyMapping(_0), input2]);
var MappedOptional = (input) => If(If(If(Const("+", input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const("-", input), ([_0, input2]) => If(Const("?", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const("?", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])))), ([_0, input2]) => [MappedOptionalMapping(_0), input2]);
var MappedAs = (input) => If(If(If(Const("as", input), ([_0, input2]) => If(Type(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [MappedAsMapping(_0), input2]);
var _Mapped_ = (input) => If(If(Const("{", input), ([_0, input2]) => If(MappedReadonly(input2), ([_1, input3]) => If(Const("[", input3), ([_2, input4]) => If(Ident(input4), ([_3, input5]) => If(Const("in", input5), ([_4, input6]) => If(Type(input6), ([_5, input7]) => If(MappedAs(input7), ([_6, input8]) => If(Const("]", input8), ([_7, input9]) => If(MappedOptional(input9), ([_8, input10]) => If(Const(":", input10), ([_9, input11]) => If(Type(input11), ([_10, input12]) => If(OptionalSemiColon(input12), ([_11, input13]) => If(Const("}", input13), ([_12, input14]) => [[_0, _1, _2, _3, _4, _5, _6, _7, _8, _9, _10, _11, _12], input14]))))))))))))), ([_0, input2]) => [_Mapped_Mapping(_0), input2]);
var Reference = (input) => If(Ident(input), ([_0, input2]) => [ReferenceMapping(_0), input2]);
var WithBigInt = (input) => If(BigInt3(input), ([_0, input2]) => [WithBigIntMapping(_0), input2]);
var WithNumber = (input) => If(Number3(input), ([_0, input2]) => [WithNumberMapping(_0), input2]);
var WithBoolean = (input) => If(If(Const("true", input), ([_0, input2]) => [_0, input2], () => If(Const("false", input), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [WithBooleanMapping(_0), input2]);
var WithString = (input) => If(String3(['"', "'"], input), ([_0, input2]) => [WithStringMapping(_0), input2]);
var WithNull = (input) => If(Const("null", input), ([_0, input2]) => [WithNullMapping(_0), input2]);
var WithUndefined = (input) => If(Const("undefined", input), ([_0, input2]) => [WithUndefinedMapping(_0), input2]);
var WithProperty = (input) => If(If(PropertyKey(input), ([_0, input2]) => If(Const(":", input2), ([_1, input3]) => If(WithValue(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [WithPropertyMapping(_0), input2]);
var WithPropertyList_0 = (input, result = []) => If(If(WithProperty(input), ([_0, input2]) => If(PropertyDelimiter(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => WithPropertyList_0(input2, [...result, _0]), () => [result, input]);
var WithPropertyList = (input) => If(If(WithPropertyList_0(input), ([_0, input2]) => If(If(If(WithProperty(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [WithPropertyListMapping(_0), input2]);
var WithObject = (input) => If(If(Const("{", input), ([_0, input2]) => If(WithPropertyList(input2), ([_1, input3]) => If(Const("}", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [WithObjectMapping(_0), input2]);
var WithElementList_0 = (input, result = []) => If(If(WithValue(input), ([_0, input2]) => If(Const(",", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => WithElementList_0(input2, [...result, _0]), () => [result, input]);
var WithElementList = (input) => If(If(WithElementList_0(input), ([_0, input2]) => If(If(If(WithValue(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [WithElementListMapping(_0), input2]);
var WithArray = (input) => If(If(Const("[", input), ([_0, input2]) => If(WithElementList(input2), ([_1, input3]) => If(Const("]", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [WithArrayMapping(_0), input2]);
var WithValue = (input) => If(If(WithBigInt(input), ([_0, input2]) => [_0, input2], () => If(WithNumber(input), ([_0, input2]) => [_0, input2], () => If(WithBoolean(input), ([_0, input2]) => [_0, input2], () => If(WithString(input), ([_0, input2]) => [_0, input2], () => If(WithNull(input), ([_0, input2]) => [_0, input2], () => If(WithUndefined(input), ([_0, input2]) => [_0, input2], () => If(WithObject(input), ([_0, input2]) => [_0, input2], () => If(WithArray(input), ([_0, input2]) => [_0, input2], () => [])))))))), ([_0, input2]) => [WithValueMapping(_0), input2]);
var PatternBigInt = (input) => If(Const("-?(?:0|[1-9][0-9]*)n", input), ([_0, input2]) => [PatternBigIntMapping(_0), input2]);
var PatternString = (input) => If(Const(".*", input), ([_0, input2]) => [PatternStringMapping(_0), input2]);
var PatternNumber = (input) => If(Const("-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?", input), ([_0, input2]) => [PatternNumberMapping(_0), input2]);
var PatternInteger = (input) => If(Const("-?(?:0|[1-9][0-9]*)", input), ([_0, input2]) => [PatternIntegerMapping(_0), input2]);
var PatternNever = (input) => If(Const("(?!)", input), ([_0, input2]) => [PatternNeverMapping(_0), input2]);
var PatternText = (input) => If(Until_1(["-?(?:0|[1-9][0-9]*)n", ".*", "-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?", "-?(?:0|[1-9][0-9]*)", "(?!)", "(", ")", "$", "|"], input), ([_0, input2]) => [PatternTextMapping(_0), input2]);
var PatternBase = (input) => If(If(PatternBigInt(input), ([_0, input2]) => [_0, input2], () => If(PatternString(input), ([_0, input2]) => [_0, input2], () => If(PatternNumber(input), ([_0, input2]) => [_0, input2], () => If(PatternInteger(input), ([_0, input2]) => [_0, input2], () => If(PatternNever(input), ([_0, input2]) => [_0, input2], () => If(PatternGroup(input), ([_0, input2]) => [_0, input2], () => If(PatternText(input), ([_0, input2]) => [_0, input2], () => []))))))), ([_0, input2]) => [PatternBaseMapping(_0), input2]);
var PatternGroup = (input) => If(If(Const("(", input), ([_0, input2]) => If(PatternBody(input2), ([_1, input3]) => If(Const(")", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [PatternGroupMapping(_0), input2]);
var PatternUnion = (input) => If(If(If(PatternTerm(input), ([_0, input2]) => If(Const("|", input2), ([_1, input3]) => If(PatternUnion(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [_0, input2], () => If(If(PatternTerm(input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => []))), ([_0, input2]) => [PatternUnionMapping(_0), input2]);
var PatternTerm = (input) => If(If(PatternBase(input), ([_0, input2]) => If(PatternBody(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [PatternTermMapping(_0), input2]);
var PatternBody = (input) => If(If(PatternUnion(input), ([_0, input2]) => [_0, input2], () => If(PatternTerm(input), ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [PatternBodyMapping(_0), input2]);
var Pattern = (input) => If(If(Const("^", input), ([_0, input2]) => If(PatternBody(input2), ([_1, input3]) => If(Const("$", input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [PatternMapping(_0), input2]);
var InterfaceDeclarationHeritageList_0 = (input, result = []) => If(If(Type(input), ([_0, input2]) => If(Const(",", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => InterfaceDeclarationHeritageList_0(input2, [...result, _0]), () => [result, input]);
var InterfaceDeclarationHeritageList = (input) => If(If(InterfaceDeclarationHeritageList_0(input), ([_0, input2]) => If(If(If(Type(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [InterfaceDeclarationHeritageListMapping(_0), input2]);
var InterfaceDeclarationHeritage = (input) => If(If(If(Const("extends", input), ([_0, input2]) => If(InterfaceDeclarationHeritageList(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [InterfaceDeclarationHeritageMapping(_0), input2]);
var InterfaceDeclarationGeneric = (input) => If(If(Const("interface", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => If(GenericParameters(input3), ([_2, input4]) => If(InterfaceDeclarationHeritage(input4), ([_3, input5]) => If(Properties(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [InterfaceDeclarationGenericMapping(_0), input2]);
var InterfaceDeclaration = (input) => If(If(Const("interface", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => If(InterfaceDeclarationHeritage(input3), ([_2, input4]) => If(Properties(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [InterfaceDeclarationMapping(_0), input2]);
var TypeAliasDeclarationGeneric = (input) => If(If(Const("type", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => If(GenericParameters(input3), ([_2, input4]) => If(Const("=", input4), ([_3, input5]) => If(Type(input5), ([_4, input6]) => [[_0, _1, _2, _3, _4], input6]))))), ([_0, input2]) => [TypeAliasDeclarationGenericMapping(_0), input2]);
var TypeAliasDeclaration = (input) => If(If(Const("type", input), ([_0, input2]) => If(Ident(input2), ([_1, input3]) => If(Const("=", input3), ([_2, input4]) => If(Type(input4), ([_3, input5]) => [[_0, _1, _2, _3], input5])))), ([_0, input2]) => [TypeAliasDeclarationMapping(_0), input2]);
var ExportKeyword = (input) => If(If(If(Const("export", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If([[], input], ([_0, input2]) => [_0, input2], () => [])), ([_0, input2]) => [ExportKeywordMapping(_0), input2]);
var ModuleDeclarationDelimiter = (input) => If(If(If(Const(";", input), ([_0, input2]) => If(Const("\n", input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [_0, input2], () => If(If(Const(";", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => If(If(Const("\n", input), ([_0, input2]) => [[_0], input2]), ([_0, input2]) => [_0, input2], () => []))), ([_0, input2]) => [ModuleDeclarationDelimiterMapping(_0), input2]);
var ModuleDeclarationList_0 = (input, result = []) => If(If(ModuleDeclaration(input), ([_0, input2]) => If(ModuleDeclarationDelimiter(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => ModuleDeclarationList_0(input2, [...result, _0]), () => [result, input]);
var ModuleDeclarationList = (input) => If(If(ModuleDeclarationList_0(input), ([_0, input2]) => If(If(If(ModuleDeclaration(input2), ([_02, input3]) => [[_02], input3]), ([_02, input3]) => [_02, input3], () => If([[], input2], ([_02, input3]) => [_02, input3], () => [])), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ModuleDeclarationListMapping(_0), input2]);
var ModuleDeclaration = (input) => If(If(ExportKeyword(input), ([_0, input2]) => If(If(InterfaceDeclarationGeneric(input2), ([_02, input3]) => [_02, input3], () => If(InterfaceDeclaration(input2), ([_02, input3]) => [_02, input3], () => If(TypeAliasDeclarationGeneric(input2), ([_02, input3]) => [_02, input3], () => If(TypeAliasDeclaration(input2), ([_02, input3]) => [_02, input3], () => [])))), ([_1, input3]) => If(OptionalSemiColon(input3), ([_2, input4]) => [[_0, _1, _2], input4]))), ([_0, input2]) => [ModuleDeclarationMapping(_0), input2]);
var Module = (input) => If(If(ModuleDeclaration(input), ([_0, input2]) => If(ModuleDeclarationList(input2), ([_1, input3]) => [[_0, _1], input3])), ([_0, input2]) => [ModuleMapping(_0), input2]);
var Script = (input) => If(If(Module(input), ([_0, input2]) => [_0, input2], () => If(GenericType(input), ([_0, input2]) => [_0, input2], () => If(Type(input), ([_0, input2]) => [_0, input2], () => []))), ([_0, input2]) => [ScriptMapping(_0), input2]);

// node_modules/typebox/build/type/engine/patterns/template.mjs
function ParseTemplateIntoTypes(template) {
  const parsed = TemplateLiteralTypes(`\`${template}\``);
  const result = guard_exports.IsEqual(parsed.length, 2) ? parsed[0] : Unreachable();
  return result;
}

// node_modules/typebox/build/type/engine/template_literal/encode.mjs
function JoinString(input) {
  return input.join("|");
}
function UnwrapTemplateLiteralPattern(pattern) {
  return pattern.slice(1, pattern.length - 1);
}
function EncodeLiteral(value, right, pattern) {
  return EncodeTypes(right, `${pattern}${value}`);
}
function EncodeBigInt(right, pattern) {
  return EncodeTypes(right, `${pattern}${BigIntPattern}`);
}
function EncodeInteger(right, pattern) {
  return EncodeTypes(right, `${pattern}${IntegerPattern}`);
}
function EncodeNumber(right, pattern) {
  return EncodeTypes(right, `${pattern}${NumberPattern}`);
}
function EncodeBoolean(right, pattern) {
  return EncodeType(Union([Literal("false"), Literal("true")]), right, pattern);
}
function EncodeString(right, pattern) {
  return EncodeTypes(right, `${pattern}${StringPattern}`);
}
function EncodeTemplateLiteral(templatePattern, right, pattern) {
  return EncodeTypes(right, `${pattern}${UnwrapTemplateLiteralPattern(templatePattern)}`);
}
function EncodeTemplateLiteralDeferred(types2, right, pattern) {
  const templateLiteral = TemplateLiteralAction(types2, {});
  const result = EncodeType(templateLiteral, right, pattern);
  return result;
}
function EncodeEnum(values, right, pattern) {
  const evaluated = EvaluateEnum(values);
  return EncodeType(evaluated, right, pattern);
}
function EncodeUnion(types2, right, pattern, result = []) {
  return guard_exports.ShiftLeft(types2, (head, tail) => EncodeUnion(tail, right, pattern, [...result, EncodeType(head, [], "")]), () => EncodeTypes(right, `${pattern}(${JoinString(result)})`));
}
function EncodeType(type, right, pattern) {
  return IsEnum(type) ? EncodeEnum(type.enum, right, pattern) : IsInteger2(type) ? EncodeInteger(right, pattern) : IsLiteral(type) ? EncodeLiteral(type.const, right, pattern) : IsBigInt2(type) ? EncodeBigInt(right, pattern) : IsBoolean3(type) ? EncodeBoolean(right, pattern) : IsNumber3(type) ? EncodeNumber(right, pattern) : IsString3(type) ? EncodeString(right, pattern) : IsTemplateLiteral(type) ? EncodeTemplateLiteral(type.pattern, right, pattern) : IsTemplateLiteralDeferred(type) ? EncodeTemplateLiteralDeferred(type.parameters[0], right, pattern) : IsUnion(type) ? EncodeUnion(type.anyOf, right, pattern) : NeverPattern;
}
function EncodeTypes(types2, pattern) {
  return guard_exports.ShiftLeft(types2, (left, right) => EncodeType(left, right, pattern), () => pattern);
}
function EncodePattern(types2) {
  const encoded = EncodeTypes(types2, "");
  const result = `^${encoded}$`;
  return result;
}
function TemplateLiteralEncode(types2) {
  const pattern = EncodePattern(types2);
  const result = TemplateLiteralCreate(pattern);
  return result;
}

// node_modules/typebox/build/type/engine/template_literal/instantiate.mjs
function TemplateLiteralAction(types2, options) {
  const result = CanInstantiate(types2) ? memory_exports.Update(TemplateLiteralEncode(types2), {}, options) : TemplateLiteralDeferred(types2, options);
  return result;
}
function TemplateLiteralInstantiate(context, state, types2, options) {
  const instantiatedTypes = InstantiateTypes(context, state, types2);
  return TemplateLiteralAction(instantiatedTypes, options);
}

// node_modules/typebox/build/type/types/template_literal.mjs
function TemplateLiteralDeferred(types2, options = {}) {
  return Deferred("TemplateLiteral", [types2], options);
}
function IsTemplateLiteralDeferred(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "action") && guard_exports.IsEqual(value.action, "TemplateLiteral");
}
function TemplateLiteralFromTypes(types2) {
  return TemplateLiteralAction(types2, {});
}
function TemplateLiteralFromString(template) {
  const types2 = ParseTemplateIntoTypes(template);
  return TemplateLiteralFromTypes(types2);
}
function TemplateLiteral2(input, options = {}) {
  const type = guard_exports.IsString(input) ? TemplateLiteralFromString(input) : TemplateLiteralFromTypes(input);
  return memory_exports.Update(type, {}, options);
}
function IsTemplateLiteral(value) {
  return IsKind(value, "TemplateLiteral");
}

// node_modules/typebox/build/type/extends/result.mjs
var result_exports = {};
__export(result_exports, {
  ExtendsFalse: () => ExtendsFalse,
  ExtendsTrue: () => ExtendsTrue,
  ExtendsUnion: () => ExtendsUnion,
  IsExtendsFalse: () => IsExtendsFalse,
  IsExtendsTrue: () => IsExtendsTrue,
  IsExtendsTrueLike: () => IsExtendsTrueLike,
  IsExtendsUnion: () => IsExtendsUnion,
  Match: () => Match3
});
function ExtendsUnion(inferred) {
  return memory_exports.Create({ ["~kind"]: "ExtendsUnion" }, { inferred });
}
function IsExtendsUnion(value) {
  return guard_exports.IsObject(value) && guard_exports.HasPropertyKey(value, "~kind") && guard_exports.HasPropertyKey(value, "inferred") && guard_exports.IsEqual(value["~kind"], "ExtendsUnion") && guard_exports.IsObject(value.inferred);
}
function ExtendsTrue(inferred) {
  return memory_exports.Create({ ["~kind"]: "ExtendsTrue" }, { inferred });
}
function IsExtendsTrue(value) {
  return guard_exports.IsObject(value) && guard_exports.HasPropertyKey(value, "~kind") && guard_exports.HasPropertyKey(value, "inferred") && guard_exports.IsEqual(value["~kind"], "ExtendsTrue") && guard_exports.IsObject(value.inferred);
}
function ExtendsFalse() {
  return memory_exports.Create({ ["~kind"]: "ExtendsFalse" }, {});
}
function IsExtendsFalse(value) {
  return guard_exports.IsObject(value) && guard_exports.HasPropertyKey(value, "~kind") && guard_exports.IsEqual(value["~kind"], "ExtendsFalse");
}
function IsExtendsTrueLike(value) {
  return IsExtendsUnion(value) || IsExtendsTrue(value);
}
function Match3(result, true_, false_) {
  return IsExtendsTrueLike(result) ? true_(result.inferred) : false_();
}

// node_modules/typebox/build/type/extends/extends_right.mjs
function ExtendsRightInfer(inferred, name, left, right) {
  return Match3(ExtendsLeft(inferred, left, right), (checkInferred) => ExtendsTrue(memory_exports.Assign(memory_exports.Assign(inferred, checkInferred), { [name]: left })), () => ExtendsFalse());
}
function ExtendsRightAny(inferred, _left) {
  return ExtendsTrue(inferred);
}
function ExtendsRightDependent(inferred, left, if_, then_, else_) {
  return Match3(ExtendsLeft(inferred, left, if_), (inferred2) => Match3(ExtendsLeft(inferred2, left, then_), (inferred3) => ExtendsTrue(inferred3), () => ExtendsFalse()), () => Match3(ExtendsLeft(inferred, left, else_), (inferred2) => ExtendsTrue(inferred2), () => ExtendsFalse()));
}
function ExtendsRightEnum(inferred, left, right) {
  const evaluated = EvaluateEnum(right);
  return ExtendsLeft(inferred, left, evaluated);
}
function ExtendsRightIntersect(inferred, left, right) {
  return guard_exports.ShiftLeft(right, (head, tail) => Match3(ExtendsLeft(inferred, left, head), (inferred2) => ExtendsRightIntersect(inferred2, left, tail), () => ExtendsFalse()), () => ExtendsTrue(inferred));
}
function ExtendsRightTemplateLiteral(inferred, left, right) {
  const evaluated = EvaluateTemplateLiteral(right);
  return ExtendsLeft(inferred, left, evaluated);
}
function ExtendsRightUnion(inferred, left, right) {
  return guard_exports.ShiftLeft(right, (head, tail) => Match3(ExtendsLeft(inferred, left, head), (inferred2) => ExtendsTrue(inferred2), () => ExtendsRightUnion(inferred, left, tail)), () => ExtendsFalse());
}
function ExtendsRight(inferred, left, right) {
  return IsAny(right) ? ExtendsRightAny(inferred, left) : IsDependent(right) ? ExtendsRightDependent(inferred, left, right.if, right.then, right.else) : IsEnum(right) ? ExtendsRightEnum(inferred, left, right.enum) : IsInfer(right) ? ExtendsRightInfer(inferred, right.name, left, right.extends) : IsIntersect(right) ? ExtendsRightIntersect(inferred, left, right.allOf) : IsTemplateLiteral(right) ? ExtendsRightTemplateLiteral(inferred, left, right.pattern) : IsUnion(right) ? ExtendsRightUnion(inferred, left, right.anyOf) : IsUnknown(right) ? ExtendsTrue(inferred) : ExtendsFalse();
}

// node_modules/typebox/build/type/extends/any.mjs
function ExtendsAny(inferred, left, right) {
  return IsInfer(right) ? ExtendsRight(inferred, left, right) : IsAny(right) ? ExtendsTrue(inferred) : IsUnknown(right) ? ExtendsTrue(inferred) : ExtendsUnion(inferred);
}

// node_modules/typebox/build/type/extends/array.mjs
function ExtendsImmutable(left, right) {
  const isImmutableLeft = IsImmutable(left);
  const isImmutableRight = IsImmutable(right);
  return isImmutableLeft && isImmutableRight ? true : !isImmutableLeft && isImmutableRight ? true : isImmutableLeft && !isImmutableRight ? false : true;
}
function ExtendsArray(inferred, arrayLeft, left, right) {
  return IsArray2(right) ? ExtendsImmutable(arrayLeft, right) ? ExtendsLeft(inferred, left, right.items) : ExtendsFalse() : ExtendsRight(inferred, arrayLeft, right);
}

// node_modules/typebox/build/type/extends/bigint.mjs
function ExtendsBigInt(inferred, left, right) {
  return IsBigInt2(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/boolean.mjs
function ExtendsBoolean(inferred, left, right) {
  return IsBoolean3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/parameters.mjs
function ParameterCompare(inferred, left, leftRest, right, rightRest) {
  const checkLeft = IsInfer(right) ? left : right;
  const checkRight = IsInfer(right) ? right : left;
  const isLeftOptional = IsOptional(left);
  const isRightOptional = IsOptional(right);
  return !isLeftOptional && isRightOptional ? ExtendsFalse() : Match3(ExtendsLeft(inferred, checkLeft, checkRight), (inferred2) => ExtendsParameters(inferred2, leftRest, rightRest), () => ExtendsFalse());
}
function ParameterRight(inferred, left, leftRest, rightRest) {
  return guard_exports.ShiftLeft(rightRest, (head, tail) => ParameterCompare(inferred, left, leftRest, head, tail), () => IsOptional(left) ? ExtendsTrue(inferred) : ExtendsFalse());
}
function ParametersLeft(inferred, left, rightRest) {
  return guard_exports.ShiftLeft(left, (head, tail) => ParameterRight(inferred, head, tail, rightRest), () => ExtendsTrue(inferred));
}
function ExtendsParameters(inferred, left, right) {
  return ParametersLeft(inferred, left, right);
}

// node_modules/typebox/build/type/extends/return_type.mjs
function ExtendsReturnType(inferred, left, right) {
  return IsVoid(right) ? ExtendsTrue(inferred) : ExtendsLeft(inferred, left, right);
}

// node_modules/typebox/build/type/extends/constructor.mjs
function ExtendsConstructor(inferred, parameters, returnType, right) {
  return IsAny(right) ? ExtendsTrue(inferred) : IsUnknown(right) ? ExtendsTrue(inferred) : IsConstructor2(right) ? Match3(ExtendsParameters(inferred, parameters, right["parameters"]), (inferred2) => ExtendsReturnType(inferred2, returnType, right["instanceType"]), () => ExtendsFalse()) : ExtendsFalse();
}

// node_modules/typebox/build/type/extends/dependent.mjs
function ExtendsDependent(inferred, if_, then_, else_, right) {
  return Match3(ExtendsLeft(inferred, if_, right), () => ExtendsLeft(inferred, then_, right), () => ExtendsLeft(inferred, else_, right));
}

// node_modules/typebox/build/type/extends/enum.mjs
function ExtendsEnum(inferred, left, right) {
  const evaluated = EvaluateEnum(left);
  return ExtendsLeft(inferred, evaluated, right);
}

// node_modules/typebox/build/type/extends/function.mjs
function ExtendsFunction(inferred, parameters, returnType, right) {
  return IsAny(right) ? ExtendsTrue(inferred) : IsUnknown(right) ? ExtendsTrue(inferred) : IsFunction2(right) ? Match3(ExtendsParameters(inferred, parameters, right["parameters"]), (inferred2) => ExtendsReturnType(inferred2, returnType, right["returnType"]), () => ExtendsFalse()) : ExtendsFalse();
}

// node_modules/typebox/build/type/extends/integer.mjs
function ExtendsInteger(inferred, left, right) {
  return IsInteger2(right) ? ExtendsTrue(inferred) : IsNumber3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/intersect.mjs
function ExtendsIntersect(inferred, left, right) {
  const evaluated = EvaluateIntersect(left);
  return ExtendsLeft(inferred, evaluated, right);
}

// node_modules/typebox/build/type/extends/literal.mjs
function ExtendsLiteralValue(inferred, left, right) {
  return left === right ? ExtendsTrue(inferred) : ExtendsFalse();
}
function ExtendsLiteralBigInt(inferred, left, right) {
  return IsLiteral(right) ? ExtendsLiteralValue(inferred, left, right.const) : IsBigInt2(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, Literal(left), right);
}
function ExtendsLiteralBoolean(inferred, left, right) {
  return IsLiteral(right) ? ExtendsLiteralValue(inferred, left, right.const) : IsBoolean3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, Literal(left), right);
}
function ExtendsLiteralNumber(inferred, left, right) {
  return IsLiteral(right) ? ExtendsLiteralValue(inferred, left, right.const) : IsNumber3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, Literal(left), right);
}
function ExtendsLiteralString(inferred, left, right) {
  return IsLiteral(right) ? ExtendsLiteralValue(inferred, left, right.const) : IsString3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, Literal(left), right);
}
function ExtendsLiteral(inferred, left, right) {
  return guard_exports.IsBigInt(left.const) ? ExtendsLiteralBigInt(inferred, left.const, right) : guard_exports.IsBoolean(left.const) ? ExtendsLiteralBoolean(inferred, left.const, right) : guard_exports.IsNumber(left.const) ? ExtendsLiteralNumber(inferred, left.const, right) : guard_exports.IsString(left.const) ? ExtendsLiteralString(inferred, left.const, right) : Unreachable();
}

// node_modules/typebox/build/type/extends/never.mjs
function ExtendsNever(inferred, left, right) {
  return IsInfer(right) ? ExtendsRight(inferred, left, right) : ExtendsTrue(inferred);
}

// node_modules/typebox/build/type/extends/null.mjs
function ExtendsNull(inferred, left, right) {
  return IsNull2(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/number.mjs
function ExtendsNumber(inferred, left, right) {
  return IsNumber3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/object.mjs
function ExtendsPropertyOptional(inferred, left, right) {
  return IsOptional(left) ? IsOptional(right) ? ExtendsTrue(inferred) : ExtendsFalse() : ExtendsTrue(inferred);
}
function ExtendsProperty(inferred, left, right) {
  return (
    // Right TInfer<TNever> is TExtendsFalse
    IsInfer(right) && IsNever(right.extends) ? ExtendsFalse() : Match3(ExtendsLeft(inferred, left, right), (inferred2) => ExtendsPropertyOptional(inferred2, left, right), () => ExtendsFalse())
  );
}
function ExtractInferredProperties(keys, properties) {
  return keys.reduce((result, key) => {
    return key in properties ? IsExtendsTrueLike(properties[key]) ? { ...result, ...properties[key].inferred } : Unreachable() : Unreachable();
  }, {});
}
function ExtendsPropertiesComparer(inferred, left, right) {
  const properties = {};
  for (const rightKey of guard_exports.Keys(right)) {
    properties[rightKey] = rightKey in left ? ExtendsProperty({}, left[rightKey], right[rightKey]) : IsOptional(right[rightKey]) ? IsInfer(right[rightKey]) ? ExtendsTrue(memory_exports.Assign(inferred, { [right[rightKey].name]: right[rightKey].extends })) : ExtendsTrue(inferred) : ExtendsFalse();
  }
  const checked = guard_exports.Values(properties).every((result) => IsExtendsTrueLike(result));
  const extracted = checked ? ExtractInferredProperties(guard_exports.Keys(properties), properties) : {};
  return checked ? ExtendsTrue(extracted) : ExtendsFalse();
}
function ExtendsProperties(inferred, left, right) {
  const compared = ExtendsPropertiesComparer(inferred, left, right);
  return IsExtendsTrueLike(compared) ? ExtendsTrue(memory_exports.Assign(inferred, compared.inferred)) : ExtendsFalse();
}
function ExtendsObjectToObject(inferred, left, right) {
  return ExtendsProperties(inferred, left, right);
}
function RecordMergeInferred(left, right) {
  return guard_exports.Keys(right).reduce((result, key) => {
    return {
      ...result,
      [key]: guard_exports.HasPropertyKey(left, key) ? IsUnion(result[key]) ? Union([...result[key].anyOf, right[key]]) : Union([left[key], right[key]]) : right[key]
    };
  }, left);
}
function ExtendsRecordComparer(properties, keys, type, result) {
  return guard_exports.ShiftLeft(keys, (left, right) => Match3(ExtendsLeft({}, properties[left], type), (inferred) => ExtendsRecordComparer(properties, right, type, RecordMergeInferred(result, inferred)), () => ExtendsFalse()), () => ExtendsTrue(result));
}
function ExtendsObjectToRecord(inferred, properties, _pattern, value) {
  const keys = guard_exports.Keys(properties);
  const result = ExtendsRecordComparer(properties, keys, value, inferred);
  return result;
}
function ExtendsObject(inferred, left, right) {
  return IsRecord(right) ? ExtendsObjectToRecord(inferred, left, RecordPattern(right), RecordValue(right)) : IsObject2(right) ? ExtendsObjectToObject(inferred, left, right.properties) : ExtendsRight(inferred, _Object_(left), right);
}

// node_modules/typebox/build/type/extends/record.mjs
function FromObject2(inferred, properties) {
  return guard_exports.IsEqual(guard_exports.Keys(properties).length, 0) ? ExtendsTrue(inferred) : ExtendsFalse();
}
function FromRecord(inferred, _leftKey, leftValue, _rightKey, rightValue) {
  return ExtendsLeft(inferred, leftValue, rightValue);
}
function ExtendsRecord(inferred, leftPattern, leftValue, right) {
  return IsRecord(right) ? FromRecord(inferred, RecordPatternToType(leftPattern), leftValue, RecordPatternToType(RecordPattern(right)), RecordValue(right)) : IsObject2(right) ? FromObject2(inferred, right.properties) : IsAny(right) ? ExtendsTrue(inferred) : IsUnknown(right) ? ExtendsTrue(inferred) : ExtendsFalse();
}

// node_modules/typebox/build/type/extends/string.mjs
function ExtendsString(inferred, left, right) {
  return IsString3(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/symbol.mjs
function ExtendsSymbol(inferred, left, right) {
  return IsSymbol2(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/template_literal.mjs
function ExtendsTemplateLiteral(inferred, left, right) {
  const evaluated = EvaluateTemplateLiteral(left);
  return ExtendsLeft(inferred, evaluated, right);
}

// node_modules/typebox/build/type/extends/inference.mjs
function Inferrable(name, type) {
  return memory_exports.Create({ "~kind": "Inferrable" }, { name, type }, {});
}
function IsInferable(value) {
  return guard_exports.IsObject(value) && guard_exports.HasPropertyKey(value, "~kind") && guard_exports.HasPropertyKey(value, "name") && guard_exports.HasPropertyKey(value, "type") && guard_exports.IsEqual(value["~kind"], "Inferrable") && guard_exports.IsString(value.name) && guard_exports.IsObject(value.type);
}
function TryRestInferable(type) {
  return IsRest(type) ? IsInfer(type.items) ? IsArray2(type.items.extends) ? Inferrable(type.items.name, type.items.extends.items) : IsUnknown(type.items.extends) ? Inferrable(type.items.name, type.items.extends) : void 0 : Unreachable() : void 0;
}
function TryInferable(type) {
  return IsInfer(type) ? Inferrable(type.name, type.extends) : void 0;
}
function TryInferResults(rest, right, result = []) {
  return guard_exports.ShiftLeft(rest, (head, tail) => Match3(ExtendsLeft({}, head, right), () => TryInferResults(tail, right, [...result, head]), () => void 0), () => result);
}
function InferTupleResult(inferred, name, left, right) {
  const results = TryInferResults(left, right);
  return guard_exports.IsArray(results) ? ExtendsTrue(memory_exports.Assign(inferred, { [name]: Tuple(results) })) : ExtendsFalse();
}
function InferUnionResult(inferred, name, left, right) {
  const results = TryInferResults(left, right);
  return guard_exports.IsArray(results) ? ExtendsTrue(memory_exports.Assign(inferred, { [name]: Union(results) })) : ExtendsFalse();
}

// node_modules/typebox/build/type/extends/tuple.mjs
function Reverse(types2) {
  return [...types2].reverse();
}
function ApplyReverse(types2, reversed) {
  return reversed ? Reverse(types2) : types2;
}
function Reversed(types2) {
  const first = types2.length > 0 ? types2[0] : void 0;
  const inferrable = IsSchema(first) ? TryRestInferable(first) : void 0;
  return IsSchema(inferrable);
}
function ElementsCompare(inferred, reversed, left, leftRest, right, rightRest) {
  return Match3(ExtendsLeft(inferred, left, right), (checkInferred) => Elements(checkInferred, reversed, leftRest, rightRest), () => ExtendsFalse());
}
function ElementsLeft(inferred, reversed, leftRest, right, rightRest) {
  const inferable = TryRestInferable(right);
  return (
    // Rest Inferrable Right Means we delegate to TInferTupleResult to Generate a Result
    IsInferable(inferable) ? InferTupleResult(inferred, inferable["name"], ApplyReverse(leftRest, reversed), inferable["type"]) : guard_exports.ShiftLeft(leftRest, (head, tail) => ElementsCompare(inferred, reversed, head, tail, right, rightRest), () => ExtendsFalse())
  );
}
function ElementsRight(inferred, reversed, leftRest, rightRest) {
  return guard_exports.ShiftLeft(rightRest, (head, tail) => ElementsLeft(inferred, reversed, leftRest, head, tail), () => guard_exports.IsEqual(leftRest.length, 0) ? ExtendsTrue(inferred) : ExtendsFalse());
}
function Elements(inferred, reversed, leftRest, rightRest) {
  return ElementsRight(inferred, reversed, leftRest, rightRest);
}
function ExtendsTupleToTuple(inferred, left, right) {
  const instantiatedRight = InstantiateElements(inferred, State([], []), right);
  const reversed = Reversed(instantiatedRight);
  return Elements(inferred, reversed, ApplyReverse(left, reversed), ApplyReverse(instantiatedRight, reversed));
}
function ExtendsTupleToArray(inferred, left, right) {
  const inferrable = TryInferable(right);
  return IsInferable(inferrable) ? InferUnionResult(inferred, inferrable["name"], left, inferrable["type"]) : guard_exports.ShiftLeft(left, (head, tail) => Match3(ExtendsLeft(inferred, head, right), (inferred2) => ExtendsTupleToArray(inferred2, tail, right), () => ExtendsFalse()), () => ExtendsTrue(inferred));
}
function ExtendsTuple(inferred, left, right) {
  const instantiatedLeft = InstantiateElements(inferred, State([], []), left);
  return IsTuple(right) ? ExtendsTupleToTuple(inferred, instantiatedLeft, right.items) : IsArray2(right) ? ExtendsTupleToArray(inferred, instantiatedLeft, right.items) : ExtendsRight(inferred, Tuple(instantiatedLeft), right);
}

// node_modules/typebox/build/type/extends/undefined.mjs
function ExtendsUndefined(inferred, left, right) {
  return IsVoid(right) ? ExtendsTrue(inferred) : IsUndefined2(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/union.mjs
function ExtendsUnionSome(inferred, type, unionTypes) {
  return guard_exports.ShiftLeft(unionTypes, (head, tail) => Match3(ExtendsLeft(inferred, type, head), (inferred2) => ExtendsTrue(inferred2), () => ExtendsUnionSome(inferred, type, tail)), () => ExtendsFalse());
}
function ExtendsUnionLeft(inferred, left, right) {
  return guard_exports.ShiftLeft(left, (head, tail) => Match3(ExtendsUnionSome(inferred, head, right), (inferred2) => ExtendsUnionLeft(inferred2, tail, right), () => ExtendsFalse()), () => ExtendsTrue(inferred));
}
function ExtendsUnion2(inferred, left, right) {
  const inferrable = TryInferable(right);
  return IsInferable(inferrable) ? InferUnionResult(inferred, inferrable.name, left, inferrable.type) : IsUnion(right) ? ExtendsUnionLeft(inferred, left, right.anyOf) : ExtendsUnionLeft(inferred, left, [right]);
}

// node_modules/typebox/build/type/extends/unknown.mjs
function ExtendsUnknown(inferred, left, right) {
  return IsInfer(right) ? ExtendsRight(inferred, left, right) : IsAny(right) ? ExtendsTrue(inferred) : IsUnknown(right) ? ExtendsTrue(inferred) : ExtendsFalse();
}

// node_modules/typebox/build/type/extends/void.mjs
function ExtendsVoid(inferred, left, right) {
  return IsVoid(right) ? ExtendsTrue(inferred) : ExtendsRight(inferred, left, right);
}

// node_modules/typebox/build/type/extends/extends_left.mjs
function ExtendsLeft(inferred, left, right) {
  return IsAny(left) ? ExtendsAny(inferred, left, right) : IsArray2(left) ? ExtendsArray(inferred, left, left.items, right) : IsBigInt2(left) ? ExtendsBigInt(inferred, left, right) : IsBoolean3(left) ? ExtendsBoolean(inferred, left, right) : IsConstructor2(left) ? ExtendsConstructor(inferred, left.parameters, left.instanceType, right) : IsDependent(left) ? ExtendsDependent(inferred, left.if, left.then, left.else, right) : IsEnum(left) ? ExtendsEnum(inferred, left.enum, right) : IsFunction2(left) ? ExtendsFunction(inferred, left.parameters, left.returnType, right) : IsInteger2(left) ? ExtendsInteger(inferred, left, right) : IsIntersect(left) ? ExtendsIntersect(inferred, left.allOf, right) : IsLiteral(left) ? ExtendsLiteral(inferred, left, right) : IsNever(left) ? ExtendsNever(inferred, left, right) : IsNull2(left) ? ExtendsNull(inferred, left, right) : IsNumber3(left) ? ExtendsNumber(inferred, left, right) : IsObject2(left) ? ExtendsObject(inferred, left.properties, right) : IsRecord(left) ? ExtendsRecord(inferred, RecordPattern(left), RecordValue(left), right) : IsString3(left) ? ExtendsString(inferred, left, right) : IsSymbol2(left) ? ExtendsSymbol(inferred, left, right) : IsTemplateLiteral(left) ? ExtendsTemplateLiteral(inferred, left.pattern, right) : IsTuple(left) ? ExtendsTuple(inferred, left.items, right) : IsUndefined2(left) ? ExtendsUndefined(inferred, left, right) : IsUnion(left) ? ExtendsUnion2(inferred, left.anyOf, right) : IsUnknown(left) ? ExtendsUnknown(inferred, left, right) : IsVoid(left) ? ExtendsVoid(inferred, left, right) : ExtendsFalse();
}

// node_modules/typebox/build/type/engine/interface/instantiate.mjs
function InterfaceOperation(heritage, properties) {
  const result = EvaluateIntersect([...heritage, _Object_(properties)]);
  return result;
}
function InterfaceAction(heritage, properties, options) {
  const result = CanInstantiate(heritage) ? memory_exports.Update(InterfaceOperation(heritage, properties), {}, options) : InterfaceDeferred(heritage, properties, options);
  return result;
}
function InterfaceInstantiate(context, state, heritage, properties, options) {
  const instantiatedHeritage = InstantiateTypes(context, state, heritage);
  const instantiatedProperties = InstantiateProperties(context, state, properties);
  return InterfaceAction(instantiatedHeritage, instantiatedProperties, options);
}

// node_modules/typebox/build/type/action/interface.mjs
function InterfaceDeferred(heritage, properties, options = {}) {
  return Deferred("Interface", [heritage, properties], options);
}
function IsInterfaceDeferred(value) {
  return IsSchema(value) && guard_exports.HasPropertyKey(value, "action") && guard_exports.IsEqual(value.action, "Interface");
}
function Interface(heritage, properties, options = {}) {
  return InterfaceAction(heritage, properties, options);
}

// node_modules/typebox/build/type/engine/cyclic/check.mjs
function FromRef(stack, context, ref) {
  return stack.includes(ref) ? true : FromType3([...stack, ref], context, context[ref]);
}
function FromProperties(stack, context, properties) {
  const types2 = PropertyValues(properties);
  return FromTypes2(stack, context, types2);
}
function FromTypes2(stack, context, types2) {
  return guard_exports.ShiftLeft(types2, (left, right) => FromType3(stack, context, left) ? true : FromTypes2(stack, context, right), () => false);
}
function FromType3(stack, context, type) {
  return IsRef(type) ? FromRef(stack, context, type.$ref) : IsArray2(type) ? FromType3(stack, context, type.items) : IsConstructor2(type) ? FromTypes2(stack, context, [...type.parameters, type.instanceType]) : IsFunction2(type) ? FromTypes2(stack, context, [...type.parameters, type.returnType]) : IsInterfaceDeferred(type) ? FromProperties(stack, context, type.parameters[1]) : IsIntersect(type) ? FromTypes2(stack, context, type.allOf) : IsObject2(type) ? FromProperties(stack, context, type.properties) : IsUnion(type) ? FromTypes2(stack, context, type.anyOf) : IsTuple(type) ? FromTypes2(stack, context, type.items) : IsRecord(type) ? FromType3(stack, context, RecordValue(type)) : false;
}
function CyclicCheck(stack, context, type) {
  const result = FromType3(stack, context, type);
  return result;
}

// node_modules/typebox/build/type/engine/cyclic/candidates.mjs
function ResolveCandidateKeys(context, keys) {
  return keys.reduce((result, left) => {
    return CyclicCheck([left], context, context[left]) ? [...result, left] : result;
  }, []);
}
function CyclicCandidates(context) {
  const keys = PropertyKeys(context);
  const result = ResolveCandidateKeys(context, keys);
  return result;
}

// node_modules/typebox/build/type/engine/cyclic/dependencies.mjs
function FromRef2(context, ref, result) {
  return result.includes(ref) ? result : ref in context ? FromType4(context, context[ref], [...result, ref]) : Unreachable();
}
function FromProperties2(context, properties, result) {
  const types2 = PropertyValues(properties);
  return FromTypes3(context, types2, result);
}
function FromTypes3(context, types2, result) {
  return types2.reduce((result2, left) => {
    return FromType4(context, left, result2);
  }, result);
}
function FromType4(context, type, result) {
  return IsRef(type) ? FromRef2(context, type.$ref, result) : IsArray2(type) ? FromType4(context, type.items, result) : IsConstructor2(type) ? FromTypes3(context, [...type.parameters, type.instanceType], result) : IsFunction2(type) ? FromTypes3(context, [...type.parameters, type.returnType], result) : IsInterfaceDeferred(type) ? FromProperties2(context, type.parameters[1], result) : IsIntersect(type) ? FromTypes3(context, type.allOf, result) : IsObject2(type) ? FromProperties2(context, type.properties, result) : IsUnion(type) ? FromTypes3(context, type.anyOf, result) : IsTuple(type) ? FromTypes3(context, type.items, result) : IsRecord(type) ? FromType4(context, RecordValue(type), result) : result;
}
function CyclicDependencies(context, key, type) {
  const result = FromType4(context, type, [key]);
  return result;
}

// node_modules/typebox/build/type/engine/cyclic/extends.mjs
function FromRef3(_ref) {
  return Any();
}
function FromProperties3(properties) {
  return guard_exports.Keys(properties).reduce((result, key) => {
    return { ...result, [key]: FromType5(properties[key]) };
  }, {});
}
function FromTypes4(types2) {
  return types2.reduce((result, left) => {
    return [...result, FromType5(left)];
  }, []);
}
function FromType5(type) {
  return IsRef(type) ? FromRef3(type.$ref) : IsArray2(type) ? _Array_(FromType5(type.items), ArrayOptions(type)) : IsConstructor2(type) ? Constructor(FromTypes4(type.parameters), FromType5(type.instanceType)) : IsFunction2(type) ? _Function_(FromTypes4(type.parameters), FromType5(type.returnType)) : IsIntersect(type) ? Intersect(FromTypes4(type.allOf)) : IsObject2(type) ? _Object_(FromProperties3(type.properties)) : IsRecord(type) ? Record(RecordKey(type), FromType5(RecordValue(type))) : IsUnion(type) ? Union(FromTypes4(type.anyOf)) : IsTuple(type) ? Tuple(FromTypes4(type.items)) : type;
}
function CyclicAnyFromParameters(defs, ref) {
  return ref in defs ? FromType5(defs[ref]) : Unknown();
}
function CyclicExtends(type) {
  return CyclicAnyFromParameters(type.$defs, type.$ref);
}

// node_modules/typebox/build/type/engine/cyclic/instantiate.mjs
function CyclicInterface(context, heritage, properties) {
  const instantiatedHeritage = InstantiateTypes(context, State([], []), heritage);
  const instantiatedProperties = InstantiateProperties({}, State([], []), properties);
  const evaluatedInterface = EvaluateIntersect([...instantiatedHeritage, _Object_(instantiatedProperties)]);
  return evaluatedInterface;
}
function CyclicDefinitions(context, dependencies) {
  const keys = guard_exports.Keys(context).filter((key) => dependencies.includes(key));
  return keys.reduce((result, key) => {
    const type = context[key];
    const instantiatedType = IsInterfaceDeferred(type) ? CyclicInterface(context, type.parameters[0], type.parameters[1]) : type;
    return { ...result, [key]: instantiatedType };
  }, {});
}
function InstantiateCyclic(context, ref, type) {
  const dependencies = CyclicDependencies(context, ref, type);
  const definitions = CyclicDefinitions(context, dependencies);
  const result = Cyclic(definitions, ref);
  return result;
}

// node_modules/typebox/build/type/engine/cyclic/target.mjs
function Resolve(defs, ref) {
  return ref in defs ? IsRef(defs[ref]) ? Resolve(defs, defs[ref].$ref) : defs[ref] : Never();
}
function CyclicTarget(defs, ref) {
  const result = Resolve(defs, ref);
  return result;
}

// node_modules/typebox/build/type/extends/extends.mjs
function Canonical(type) {
  return IsCyclic(type) ? CyclicExtends(type) : IsUnsafe(type) ? Unknown() : type;
}
function Extends(inferred, left, right) {
  const canonicalLeft = Canonical(left);
  const canonicalRight = Canonical(right);
  return ExtendsLeft(inferred, canonicalLeft, canonicalRight);
}

// node_modules/typebox/build/type/engine/evaluate/compare.mjs
var ResultEqual = "equal";
var ResultDisjoint = "disjoint";
var ResultLeftInside = "left-inside";
var ResultRightInside = "right-inside";
function Compare(left, right) {
  const extendsCheck = [
    IsUnknown(left) ? result_exports.ExtendsFalse() : Extends({}, left, right),
    IsUnknown(left) ? result_exports.ExtendsTrue({}) : Extends({}, right, left)
  ];
  return result_exports.IsExtendsTrueLike(extendsCheck[0]) && result_exports.IsExtendsTrueLike(extendsCheck[1]) ? ResultEqual : result_exports.IsExtendsTrueLike(extendsCheck[0]) && result_exports.IsExtendsFalse(extendsCheck[1]) ? ResultLeftInside : result_exports.IsExtendsFalse(extendsCheck[0]) && result_exports.IsExtendsTrueLike(extendsCheck[1]) ? ResultRightInside : ResultDisjoint;
}

// node_modules/typebox/build/type/engine/evaluate/broaden.mjs
function BroadFilter(type, types2) {
  return types2.filter((left) => {
    return Compare(type, left) === ResultRightInside ? false : true;
  });
}
function IsBroadestType(type, types2) {
  const result = types2.some((left) => {
    const result2 = Compare(type, left);
    return guard_exports.IsEqual(result2, ResultLeftInside) || guard_exports.IsEqual(result2, ResultEqual);
  });
  return guard_exports.IsEqual(result, false);
}
function BroadenType(type, types2) {
  const evaluated = EvaluateType(type);
  return IsAny(evaluated) ? [evaluated] : IsBroadestType(evaluated, types2) ? [...BroadFilter(evaluated, types2), evaluated] : types2;
}
function BroadenTypes(types2) {
  return types2.reduce((result, left) => {
    return IsObject2(left) ? [...result, left] : (
      // push
      IsNever(left) ? result : (
        // ignore
        BroadenType(left, result)
      )
    );
  }, []);
}
function Broaden(types2) {
  const broadened = BroadenTypes(types2);
  const flattened = Flatten(broadened);
  return flattened;
}

// node_modules/typebox/build/type/engine/evaluate/instantiate.mjs
function EvaluateAction(type, options) {
  const result = memory_exports.Update(EvaluateType(type), {}, options);
  return result;
}
function EvaluateInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return EvaluateAction(instantiatedType, options);
}

// node_modules/typebox/build/type/engine/call/distribute_arguments.mjs
function CollectDistributionNames(expression, result = []) {
  return (
    // Conditional
    IsDeferred(expression) && guard_exports.IsEqual(expression.action, "Conditional") ? IsRef(expression.parameters[0]) ? CollectDistributionNames(expression.parameters[2], CollectDistributionNames(expression.parameters[3], [...result, expression.parameters[0]["$ref"]])) : CollectDistributionNames(expression.parameters[2], CollectDistributionNames(expression.parameters[3], result)) : IsDeferred(expression) && guard_exports.IsEqual(expression.action, "Mapped") ? IsDeferred(expression.parameters[1]) && guard_exports.IsEqual(expression.parameters[1].action, "KeyOf") && IsRef(expression.parameters[1].parameters[0]) ? [...result, expression.parameters[1].parameters[0]["$ref"]] : result : result
  );
}
function BuildDistributionArray(parameters, names) {
  return parameters.reduce((result, left) => [...result, names.includes(left.name)], []);
}
function ZipDistributionArray(arguments_, distributionArray, result = []) {
  return guard_exports.ShiftLeft(arguments_, (argumentLeft, argumentRight) => guard_exports.ShiftLeft(distributionArray, (booleanLeft, booleanRight) => ZipDistributionArray(argumentRight, booleanRight, [...result, [booleanLeft, argumentLeft]]), () => result), () => result);
}
function Expand(type) {
  return IsUnion(type) ? [...type.anyOf] : [type];
}
function Append(current, type) {
  return current.reduce((result, left) => [...result, [...left, type]], []);
}
function Cross(current, variants) {
  return variants.reduce((result, left) => {
    return [...result, ...Append(current, left)];
  }, []);
}
function Distribute2(zipped) {
  return zipped.reduce((result, left) => {
    return guard_exports.IsEqual(left[0], true) ? Cross(result, Expand(left[1])) : Cross(result, [left[1]]);
  }, [[]]);
}
function DistributeArguments(parameters, arguments_, expression) {
  const distributionNames = CollectDistributionNames(expression);
  const distributionArray = BuildDistributionArray(parameters, distributionNames);
  const zippedArguments = ZipDistributionArray(arguments_, distributionArray);
  return IsDeferred(expression) && guard_exports.IsEqual(expression.action, "Conditional") ? Distribute2(zippedArguments) : IsDeferred(expression) && guard_exports.IsEqual(expression.action, "Mapped") ? Distribute2(zippedArguments) : [arguments_];
}

// node_modules/typebox/build/type/engine/call/resolve_target.mjs
function FromNotResolvable() {
  return ["(not-resolvable)", Never()];
}
function FromNotGeneric() {
  return ["(not-generic)", Never()];
}
function FromGeneric(name, parameters, expression) {
  return [name, Generic(parameters, expression)];
}
function FromRef4(context, ref, arguments_) {
  return ref in context ? FromType6(context, ref, context[ref], arguments_) : FromNotResolvable();
}
function FromType6(context, name, target, arguments_) {
  return IsGeneric(target) ? FromGeneric(name, target.parameters, target.expression) : IsRef(target) ? FromRef4(context, target.$ref, arguments_) : FromNotGeneric();
}
function ResolveTarget(context, target, arguments_) {
  return FromType6(context, "(anonymous)", target, arguments_);
}

// node_modules/typebox/build/type/engine/call/resolve_arguments.mjs
function AssertArgumentExtends(name, type, extends_) {
  if (IsInfer(type) || IsCall(type) || result_exports.IsExtendsTrueLike(Extends({}, type, extends_)))
    return;
  const cause = { parameter: name, expect: extends_, actual: type };
  throw new Error(`Argument for parameter ${name} does not satisfy constraint`, { cause });
}
function BindArgument(context, state, name, extends_, type) {
  const instantiatedArgument = InstantiateType(context, state, type);
  AssertArgumentExtends(name, instantiatedArgument, extends_);
  return memory_exports.Assign(context, { [name]: instantiatedArgument });
}
function BindArguments(context, state, parameterLeft, parameterRight, arguments_) {
  const instantiatedExtends = InstantiateType(context, state, parameterLeft.extends);
  const instantiatedEquals = InstantiateType(context, state, parameterLeft.equals);
  return guard_exports.ShiftLeft(arguments_, (left, right) => BindParameters(BindArgument(context, state, parameterLeft["name"], instantiatedExtends, left), state, parameterRight, right), () => BindParameters(BindArgument(context, state, parameterLeft["name"], instantiatedExtends, instantiatedEquals), state, parameterRight, []));
}
function BindParameters(context, state, parameters, arguments_) {
  return guard_exports.ShiftLeft(parameters, (left, right) => BindArguments(context, state, left, right, arguments_), () => context);
}
function ResolveArgumentsContext(context, state, parameters, arguments_) {
  return BindParameters(context, state, parameters, arguments_);
}

// node_modules/typebox/build/type/engine/call/instantiate.mjs
function Peek(state) {
  const result = guard_exports.IsGreaterThan(state.callstack.length, 0) ? state.callstack[state.callstack.length - 1] : "";
  return result;
}
function IsTailCall(state, name) {
  const result = guard_exports.IsEqual(Peek(state), name);
  return result;
}
function CallDispatch(context, state, target, parameters, expression, arguments_) {
  const argumentsContext = ResolveArgumentsContext(context, state, parameters, arguments_);
  const returnType = InstantiateType(argumentsContext, State([...state["callstack"], target["$ref"]], state["visited"]), expression);
  return InstantiateType(argumentsContext, State([], []), returnType);
}
function CallDistributed(context, state, target, parameters, expression, distributedArguments) {
  return distributedArguments.reduce((result, arguments_) => [...result, CallDispatch(context, state, target, parameters, expression, arguments_)], []);
}
function CallImmediate(context, state, target, parameters, expression, arguments_) {
  const distributedArguments = DistributeArguments(parameters, arguments_, expression);
  const returnTypes = CallDistributed(context, state, target, parameters, expression, distributedArguments);
  const result = guard_exports.IsEqual(returnTypes.length, 1) ? returnTypes[0] : EvaluateUnion(returnTypes);
  return result;
}
function CallInstantiate(context, state, target, arguments_) {
  const instantiatedArguments = InstantiateTypes(context, state, arguments_);
  const resolved = ResolveTarget(context, target, arguments_);
  const name = resolved[0];
  const type = resolved[1];
  const result = IsGeneric(type) ? IsTailCall(state, name) ? CallConstruct(Ref(name), instantiatedArguments) : CallImmediate(context, state, Ref(name), type.parameters, type.expression, instantiatedArguments) : CallConstruct(target, instantiatedArguments);
  return result;
}

// node_modules/typebox/build/type/types/call.mjs
function CallConstruct(target, arguments_) {
  return memory_exports.Create({ ["~kind"]: "Call" }, { type: "call", target, arguments: arguments_ }, {});
}
function Call(target, arguments_) {
  return CallInstantiate({}, State([], []), target, arguments_);
}
function IsCall(value) {
  return IsKind(value, "Call");
}

// node_modules/typebox/build/type/engine/immutable/instantiate_remove.mjs
function RemoveImmutableOperation(type) {
  return memory_exports.Discard(type, ["~immutable"]);
}
function RemoveImmutableAction(type, options) {
  const result = memory_exports.Update(RemoveImmutableOperation(type), {}, options);
  return result;
}
function RemoveImmutableInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return RemoveImmutableAction(instantiatedType, options);
}

// node_modules/typebox/build/type/engine/intrinsics/mapping.mjs
function ApplyMapping(mapping, value) {
  return mapping(value);
}

// node_modules/typebox/build/type/engine/intrinsics/from_literal.mjs
function FromLiteral3(mapping, value) {
  return guard_exports.IsString(value) ? Literal(ApplyMapping(mapping, value)) : Literal(value);
}

// node_modules/typebox/build/type/engine/intrinsics/from_template_literal.mjs
function FromTemplateLiteral(mapping, pattern) {
  const evaluated = EvaluateTemplateLiteral(pattern);
  const result = FromType7(mapping, evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/intrinsics/from_union.mjs
function FromUnion2(mapping, types2) {
  const result = types2.map((type) => FromType7(mapping, type));
  return Union(result);
}

// node_modules/typebox/build/type/engine/intrinsics/from_type.mjs
function FromType7(mapping, type) {
  return IsLiteral(type) ? FromLiteral3(mapping, type.const) : IsTemplateLiteral(type) ? FromTemplateLiteral(mapping, type.pattern) : IsUnion(type) ? FromUnion2(mapping, type.anyOf) : type;
}

// node_modules/typebox/build/type/action/capitalize.mjs
function CapitalizeDeferred(type, options = {}) {
  return Deferred("Capitalize", [type], options);
}
function Capitalize(type, options = {}) {
  return CapitalizeAction(type, options);
}

// node_modules/typebox/build/type/action/lowercase.mjs
function LowercaseDeferred(type, options = {}) {
  return Deferred("Lowercase", [type], options);
}
function Lowercase(type, options = {}) {
  return LowercaseAction(type, options);
}

// node_modules/typebox/build/type/action/uncapitalize.mjs
function UncapitalizeDeferred(type, options = {}) {
  return Deferred("Uncapitalize", [type], options);
}
function Uncapitalize(type, options = {}) {
  return UncapitalizeAction(type, options);
}

// node_modules/typebox/build/type/action/uppercase.mjs
function UppercaseDeferred(type, options = {}) {
  return Deferred("Uppercase", [type], options);
}
function Uppercase(type, options = {}) {
  return UppercaseAction(type, options);
}

// node_modules/typebox/build/type/engine/intrinsics/instantiate.mjs
var CapitalizeMapping = (input) => input[0].toUpperCase() + input.slice(1);
var LowercaseMapping = (input) => input.toLowerCase();
var UncapitalizeMapping = (input) => input[0].toLowerCase() + input.slice(1);
var UppercaseMapping = (input) => input.toUpperCase();
function CapitalizeAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType7(CapitalizeMapping, type), {}, options) : CapitalizeDeferred(type, options);
  return result;
}
function LowercaseAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType7(LowercaseMapping, type), {}, options) : LowercaseDeferred(type, options);
  return result;
}
function UncapitalizeAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType7(UncapitalizeMapping, type), {}, options) : UncapitalizeDeferred(type, options);
  return result;
}
function UppercaseAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType7(UppercaseMapping, type), {}, options) : UppercaseDeferred(type, options);
  return result;
}
function CapitalizeInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return CapitalizeAction(instantiatedType, options);
}
function LowercaseInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return LowercaseAction(instantiatedType, options);
}
function UncapitalizeInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return UncapitalizeAction(instantiatedType, options);
}
function UppercaseInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return UppercaseAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/conditional.mjs
function ConditionalDeferred(left, right, true_, false_, options = {}) {
  return Deferred("Conditional", [left, right, true_, false_], options);
}
function Conditional(left, right, true_, false_, options = {}) {
  return ConditionalAction({}, State([], []), left, right, true_, false_, options);
}

// node_modules/typebox/build/type/engine/conditional/instantiate.mjs
function ConditionalOperation(context, state, left, right, true_, false_) {
  const extendsResult = Extends(context, left, right);
  return result_exports.IsExtendsUnion(extendsResult) ? Union([InstantiateType(extendsResult.inferred, state, true_), InstantiateType(context, state, false_)]) : result_exports.IsExtendsTrue(extendsResult) ? InstantiateType(extendsResult.inferred, state, true_) : InstantiateType(context, state, false_);
}
function ConditionalAction(context, state, left, right, true_, false_, options) {
  const result = CanInstantiate([left, right]) ? memory_exports.Update(ConditionalOperation(context, state, left, right, true_, false_), {}, options) : ConditionalDeferred(left, right, true_, false_, options);
  return result;
}
function ConditionalInstantiate(context, state, left, right, true_, false_, options) {
  const instantiatedLeft = InstantiateType(context, state, left);
  const instantiatedRight = InstantiateType(context, state, right);
  return ConditionalAction(context, state, instantiatedLeft, instantiatedRight, true_, false_, options);
}

// node_modules/typebox/build/type/action/constructor_parameters.mjs
function ConstructorParametersDeferred(type, options = {}) {
  return Deferred("ConstructorParameters", [type], options);
}
function ConstructorParameters(type, options = {}) {
  return ConstructorParametersAction(type, options);
}

// node_modules/typebox/build/type/engine/constructor_parameters/instantiate.mjs
function ConstructorParametersOperation(type) {
  const parameters = IsConstructor2(type) ? type["parameters"] : [];
  const instantiatedParameters = InstantiateElements({}, State([], []), parameters);
  const result = Tuple(instantiatedParameters);
  return result;
}
function ConstructorParametersAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(ConstructorParametersOperation(type), {}, options) : ConstructorParametersDeferred(type, options);
  return result;
}
function ConstructorParametersInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return ConstructorParametersAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/exclude.mjs
function ExcludeDeferred(left, right, options = {}) {
  return Deferred("Exclude", [left, right], options);
}
function Exclude(left, right, options = {}) {
  return ExcludeAction(left, right, options);
}

// node_modules/typebox/build/type/engine/exclude/instantiate.mjs
function ExcludeAction(left, right, options) {
  const result = CanInstantiate([left, right]) ? memory_exports.Update(ExcludeOperation(left, right), {}, options) : ExcludeDeferred(left, right, options);
  return result;
}
function ExcludeInstantiate(context, state, left, right, options) {
  const instantiatedLeft = InstantiateType(context, state, left);
  const instantiatedRight = InstantiateType(context, state, right);
  return ExcludeAction(instantiatedLeft, instantiatedRight, options);
}

// node_modules/typebox/build/type/action/extract.mjs
function ExtractDeferred(left, right, options = {}) {
  return Deferred("Extract", [left, right], options);
}
function Extract(left, right, options = {}) {
  return ExtractAction(left, right, options);
}

// node_modules/typebox/build/type/engine/extract/operation.mjs
function ExtractType(left, right) {
  const check = Extends({}, left, right);
  const result = result_exports.IsExtendsTrueLike(check) ? [left] : [];
  return result;
}
function ExtractUnion(types2, right) {
  return types2.reduce((result, head) => {
    return [...result, ...ExtractType(head, right)];
  }, []);
}
function ExtractOperation(left, right) {
  const evaluated = EvaluateType(left);
  const canonical = IsUnion(evaluated) ? evaluated.anyOf : [evaluated];
  const remaining = ExtractUnion(canonical, right);
  const result = EvaluateUnion(remaining);
  return result;
}

// node_modules/typebox/build/type/engine/extract/instantiate.mjs
function ExtractAction(left, right, options) {
  const result = CanInstantiate([left, right]) ? memory_exports.Update(ExtractOperation(left, right), {}, options) : ExtractDeferred(left, right, options);
  return result;
}
function ExtractInstantiate(context, state, left, right, options) {
  const instantiatedLeft = InstantiateType(context, state, left);
  const instantiatedRight = InstantiateType(context, state, right);
  return ExtractAction(instantiatedLeft, instantiatedRight, options);
}

// node_modules/typebox/build/type/engine/helpers/keys_to_indexer.mjs
function KeysToLiterals(keys) {
  return keys.reduce((result, left) => {
    return IsLiteralValue(left) ? [...result, Literal(left)] : result;
  }, []);
}
function KeysToIndexer(keys) {
  const literals = KeysToLiterals(keys);
  const result = Union(literals);
  return result;
}

// node_modules/typebox/build/type/action/indexed.mjs
function IndexDeferred(type, indexer, options = {}) {
  return Deferred("Index", [type, indexer], options);
}
function Index(type, indexer_or_keys, options = {}) {
  const indexer = guard_exports.IsArray(indexer_or_keys) ? KeysToIndexer(indexer_or_keys) : indexer_or_keys;
  return IndexAction(type, indexer, options);
}

// node_modules/typebox/build/type/engine/object/from_cyclic.mjs
function FromCyclic(defs, ref) {
  const target = CyclicTarget(defs, ref);
  const result = FromType8(target);
  return result;
}

// node_modules/typebox/build/type/engine/object/from_dependent.mjs
function FromDependent(if_, then_, else_) {
  const evaluated = EvaluateDependent(if_, then_, else_);
  const result = FromType8(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/object/from_intersect.mjs
function CollapseIntersectProperties(left, right) {
  const leftKeys = guard_exports.Keys(left).filter((key) => !guard_exports.HasPropertyKey(right, key));
  const rightKeys = guard_exports.Keys(right).filter((key) => !guard_exports.HasPropertyKey(left, key));
  const sharedKeys = guard_exports.Keys(left).filter((key) => guard_exports.HasPropertyKey(right, key));
  const leftProperties = leftKeys.reduce((result, key) => ({ ...result, [key]: left[key] }), {});
  const rightProperties = rightKeys.reduce((result, key) => ({ ...result, [key]: right[key] }), {});
  const sharedProperties = sharedKeys.reduce((result, key) => ({ ...result, [key]: EvaluateIntersect([left[key], right[key]]) }), {});
  const unique = memory_exports.Assign(leftProperties, rightProperties);
  const shared = memory_exports.Assign(unique, sharedProperties);
  return shared;
}
function FromIntersect(types2) {
  return types2.reduce((result, left) => {
    return CollapseIntersectProperties(result, FromType8(left));
  }, {});
}

// node_modules/typebox/build/type/engine/object/from_object.mjs
function FromObject3(properties) {
  return properties;
}

// node_modules/typebox/build/type/engine/object/from_tuple.mjs
function FromTuple(types2) {
  const object = TupleToObject(Tuple(types2));
  const result = FromType8(object);
  return result;
}

// node_modules/typebox/build/type/engine/object/from_union.mjs
function CollapseUnionProperties(left, right) {
  const sharedKeys = guard_exports.Keys(left).filter((key) => key in right);
  const result = sharedKeys.reduce((result2, key) => {
    return { ...result2, [key]: EvaluateUnion([left[key], right[key]]) };
  }, {});
  return result;
}
function ReduceVariants(types2, result) {
  return guard_exports.ShiftLeft(types2, (left, right) => ReduceVariants(right, CollapseUnionProperties(result, FromType8(left))), () => result);
}
function FromUnion3(types2) {
  return guard_exports.ShiftLeft(types2, (left, right) => ReduceVariants(right, FromType8(left)), () => Unreachable());
}

// node_modules/typebox/build/type/engine/object/from_type.mjs
function FromType8(type) {
  return IsCyclic(type) ? FromCyclic(type.$defs, type.$ref) : IsDependent(type) ? FromDependent(type.if, type.then, type.else) : IsIntersect(type) ? FromIntersect(type.allOf) : IsUnion(type) ? FromUnion3(type.anyOf) : IsTuple(type) ? FromTuple(type.items) : IsObject2(type) ? FromObject3(type.properties) : {};
}

// node_modules/typebox/build/type/engine/object/collapse.mjs
function CollapseToObject(type) {
  const properties = FromType8(type);
  const result = _Object_(properties);
  return result;
}

// node_modules/typebox/build/type/engine/helpers/keys.mjs
var integerKeyPattern = new RegExp("^(?:0|[1-9][0-9]*)$");
function ConvertToIntegerKey(value) {
  const normal = `${value}`;
  return integerKeyPattern.test(normal) ? parseInt(normal) : value;
}

// node_modules/typebox/build/type/engine/indexed/from_array.mjs
function NormalizeLiteral(value) {
  return Literal(ConvertToIntegerKey(value));
}
function NormalizeIndexerTypes(types2) {
  return types2.map((type) => NormalizeIndexer(type));
}
function NormalizeIndexer(type) {
  return IsIntersect(type) ? Intersect(NormalizeIndexerTypes(type.allOf)) : IsUnion(type) ? Union(NormalizeIndexerTypes(type.anyOf)) : IsLiteral(type) ? NormalizeLiteral(type.const) : type;
}
function FromArray2(type, indexer) {
  const normalizedIndexer = NormalizeIndexer(indexer);
  const check = Extends({}, normalizedIndexer, Number2());
  const result = (
    // indexer
    result_exports.IsExtendsTrueLike(check) ? type : IsLiteral(indexer) && guard_exports.IsEqual(indexer.const, "length") ? Number2() : Never()
  );
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_cyclic.mjs
function FromCyclic2(defs, ref) {
  const target = CyclicTarget(defs, ref);
  const result = FromType9(target);
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_dependent.mjs
function FromDependent2(if_, then_, else_) {
  const evaluated = EvaluateDependent(if_, then_, else_);
  const result = FromType9(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_enum.mjs
function FromEnum(values) {
  const evaluated = EvaluateEnum(values);
  const result = FromType9(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_intersect.mjs
function FromIntersect2(types2) {
  const evaluated = EvaluateIntersect(types2);
  const result = FromType9(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_literal.mjs
function FromLiteral4(value) {
  const result = [`${value}`];
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_template_literal.mjs
function FromTemplateLiteral2(pattern) {
  const evaluated = EvaluateTemplateLiteral(pattern);
  const result = FromType9(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/indexable/from_union.mjs
function FromUnion4(types2) {
  return types2.reduce((result, left) => {
    return [...result, ...FromType9(left)];
  }, []);
}

// node_modules/typebox/build/type/engine/indexable/from_type.mjs
function FromType9(type) {
  return IsCyclic(type) ? FromCyclic2(type.$defs, type.$ref) : IsDependent(type) ? FromDependent2(type.if, type.then, type.else) : IsEnum(type) ? FromEnum(type.enum) : IsIntersect(type) ? FromIntersect2(type.allOf) : IsLiteral(type) ? FromLiteral4(type.const) : IsTemplateLiteral(type) ? FromTemplateLiteral2(type.pattern) : IsUnion(type) ? FromUnion4(type.anyOf) : [];
}

// node_modules/typebox/build/type/engine/indexable/to_indexable_keys.mjs
function ToIndexableKeys(type) {
  const result = FromType9(type);
  return result;
}

// node_modules/typebox/build/type/engine/this/expand_this.mjs
function FromTypes5(properties, types2) {
  return types2.map((type) => FromType10(properties, type));
}
function FromType10(properties, type) {
  return IsArray2(type) ? _Array_(FromType10(properties, type.items)) : IsConstructor2(type) ? Constructor(FromTypes5(properties, type.parameters), FromType10(properties, type.instanceType)) : IsFunction2(type) ? _Function_(FromTypes5(properties, type.parameters), FromType10(properties, type.returnType)) : IsTuple(type) ? Tuple(FromTypes5(properties, type.items)) : IsUnion(type) ? Union(FromTypes5(properties, type.anyOf)) : IsIntersect(type) ? Intersect(FromTypes5(properties, type.allOf)) : IsThis(type) ? _Object_(properties) : type;
}
function ExpandThis(properties, type) {
  const result = FromType10(properties, type);
  return result;
}

// node_modules/typebox/build/type/engine/indexed/from_object.mjs
function IndexProperty(properties, key) {
  const selectedType = key in properties ? properties[key] : Never();
  const result = ExpandThis(properties, selectedType);
  return result;
}
function IndexProperties(properties, keys) {
  return keys.reduce((result, left) => {
    return [...result, IndexProperty(properties, left)];
  }, []);
}
function FromIndexer(properties, indexer) {
  const keys = ToIndexableKeys(indexer);
  const variants = IndexProperties(properties, keys);
  const result = EvaluateUnion(variants);
  return result;
}
var NumericKeyPattern = new RegExp(IntegerKey);
function NumericKeys(keys) {
  const result = keys.filter((key) => NumericKeyPattern.test(key));
  return result;
}
function FromIndexerNumber(properties) {
  const keys = PropertyKeys(properties);
  const numericKeys = NumericKeys(keys);
  const variants = IndexProperties(properties, numericKeys);
  const result = EvaluateUnion(variants);
  return result;
}
function FromObject4(properties, indexer) {
  const result = IsNumber3(indexer) ? FromIndexerNumber(properties) : FromIndexer(properties, indexer);
  return result;
}

// node_modules/typebox/build/type/engine/indexed/array_indexer.mjs
function ConvertLiteral(value) {
  return Literal(ConvertToIntegerKey(value));
}
function ArrayIndexerTypes(types2) {
  return types2.map((type) => FormatArrayIndexer(type));
}
function FormatArrayIndexer(type) {
  return IsIntersect(type) ? Intersect(ArrayIndexerTypes(type.allOf)) : IsUnion(type) ? Union(ArrayIndexerTypes(type.anyOf)) : IsLiteral(type) ? ConvertLiteral(type.const) : type;
}

// node_modules/typebox/build/type/engine/indexed/from_tuple.mjs
function IndexElementsWithIndexer(types2, indexer) {
  return types2.reduceRight((result, right, index) => {
    const check = Extends({}, Literal(index), indexer);
    return result_exports.IsExtendsTrueLike(check) ? [right, ...result] : result;
  }, []);
}
function FromTupleWithIndexer(types2, indexer) {
  const formattedArrayIndexer = FormatArrayIndexer(indexer);
  const elements = IndexElementsWithIndexer(types2, formattedArrayIndexer);
  return EvaluateUnionFast(elements);
}
function FromTupleWithoutIndexer(types2) {
  return EvaluateUnionFast(types2);
}
function FromTuple2(types2, indexer) {
  return (
    // length (intrinsic)
    IsLiteral(indexer) && guard_exports.IsEqual(indexer.const, "length") ? Literal(types2.length) : IsNumber3(indexer) || IsInteger2(indexer) ? FromTupleWithoutIndexer(types2) : FromTupleWithIndexer(types2, indexer)
  );
}

// node_modules/typebox/build/type/engine/indexed/from_type.mjs
function FromType11(type, indexer) {
  return IsArray2(type) ? FromArray2(type.items, indexer) : IsObject2(type) ? FromObject4(type.properties, indexer) : IsTuple(type) ? FromTuple2(type.items, indexer) : Never();
}

// node_modules/typebox/build/type/engine/indexed/instantiate.mjs
function NormalizeType(type) {
  const result = IsCyclic(type) || IsDependent(type) || IsIntersect(type) || IsUnion(type) ? CollapseToObject(type) : type;
  return result;
}
function IndexAction(type, indexer, options) {
  const result = CanInstantiate([type, indexer]) ? memory_exports.Update(FromType11(NormalizeType(type), indexer), {}, options) : IndexDeferred(type, indexer, options);
  return result;
}
function IndexInstantiate(context, state, type, indexer, options) {
  const instantiatedType = InstantiateType(context, state, type);
  const instantiatedIndexer = InstantiateType(context, state, indexer);
  return IndexAction(instantiatedType, instantiatedIndexer, options);
}

// node_modules/typebox/build/type/action/instance_type.mjs
function InstanceTypeDeferred(type, options = {}) {
  return Deferred("InstanceType", [type], options);
}
function InstanceType(type, options = {}) {
  return InstanceTypeAction(type, options);
}

// node_modules/typebox/build/type/engine/instance_type/instantiate.mjs
function InstanceTypeOperation(type) {
  return IsConstructor2(type) ? type["instanceType"] : Never();
}
function InstanceTypeAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(InstanceTypeOperation(type), {}, options) : InstanceTypeDeferred(type, options);
  return result;
}
function InstanceTypeInstantiate(context, state, type, options = {}) {
  const instantiatedType = InstantiateType(context, state, type);
  return InstanceTypeAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/keyof.mjs
function KeyOfDeferred(type, options = {}) {
  return Deferred("KeyOf", [type], options);
}
function KeyOf2(type, options = {}) {
  return KeyOfAction(type, options);
}

// node_modules/typebox/build/type/engine/keyof/from_any.mjs
function FromAny() {
  return Union([Number2(), String2(), Symbol2()]);
}

// node_modules/typebox/build/type/engine/keyof/from_array.mjs
function FromArray3(_type) {
  return Number2();
}

// node_modules/typebox/build/type/engine/keyof/from_object.mjs
function FromPropertyKeys(keys) {
  const result = keys.reduce((result2, left) => {
    return IsLiteralValue(left) ? [...result2, Literal(ConvertToIntegerKey(left))] : Unreachable();
  }, []);
  return result;
}
function FromObject5(properties) {
  const propertyKeys = guard_exports.Keys(properties);
  const variants = FromPropertyKeys(propertyKeys);
  const result = EvaluateUnionFast(variants);
  return result;
}

// node_modules/typebox/build/type/engine/keyof/from_record.mjs
function FromRecord2(type) {
  return RecordKey(type);
}

// node_modules/typebox/build/type/engine/keyof/from_tuple.mjs
function FromTuple3(types2) {
  const result = types2.map((_, index) => Literal(index));
  return EvaluateUnionFast(result);
}

// node_modules/typebox/build/type/engine/keyof/from_type.mjs
function FromType12(type) {
  return IsAny(type) ? FromAny() : IsArray2(type) ? FromArray3(type.items) : IsObject2(type) ? FromObject5(type.properties) : IsRecord(type) ? FromRecord2(type) : IsTuple(type) ? FromTuple3(type.items) : Never();
}

// node_modules/typebox/build/type/engine/keyof/instantiate.mjs
function NormalizeType2(type) {
  const result = IsCyclic(type) || IsDependent(type) || IsIntersect(type) || IsUnion(type) ? CollapseToObject(type) : type;
  return result;
}
function KeyOfAction(type, options) {
  return CanInstantiate([type]) ? memory_exports.Update(FromType12(NormalizeType2(type)), {}, options) : KeyOfDeferred(type, options);
}
function KeyOfInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return KeyOfAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/mapped.mjs
function MappedDeferred(identifier, type, as, property, options = {}) {
  return Deferred("Mapped", [identifier, type, as, property], options);
}
function Mapped(identifier, type, as, property, options = {}) {
  return MappedAction({}, State([], []), identifier, type, as, property, options);
}

// node_modules/typebox/build/type/engine/mapped/mapped_variants.mjs
function FromTemplateLiteral3(pattern) {
  const evaluated = EvaluateTemplateLiteral(pattern);
  const result = FromType13(evaluated);
  return result;
}
function FromUnion5(types2) {
  return types2.reduce((result, left) => {
    return [...result, ...FromType13(left)];
  }, []);
}
function FromEnum2(values) {
  const evaluated = EvaluateEnum(values);
  const result = FromType13(evaluated);
  return result;
}
function FromLiteral5(value) {
  const result = guard_exports.IsNumber(value) ? [Literal(`${value}`)] : [Literal(value)];
  return result;
}
function FromType13(type) {
  const result = IsEnum(type) ? FromEnum2(type.enum) : IsLiteral(type) ? FromLiteral5(type.const) : IsTemplateLiteral(type) ? FromTemplateLiteral3(type.pattern) : IsUnion(type) ? FromUnion5(type.anyOf) : [type];
  return result;
}
function MappedVariants(type) {
  const result = FromType13(type);
  return result;
}

// node_modules/typebox/build/type/engine/mapped/mapped_operation.mjs
function CanonicalAs(instantiatedAs) {
  const result = IsTemplateLiteral(instantiatedAs) ? EvaluateTemplateLiteral(instantiatedAs.pattern) : instantiatedAs;
  return result;
}
function MappedVariant(context, state, identifier, variant, as, property) {
  const variantContext = memory_exports.Assign(context, { [identifier["name"]]: variant });
  const instantiatedAs = InstantiateType(variantContext, state, as);
  const canonicalAs = CanonicalAs(instantiatedAs);
  const instantiatedProperty = InstantiateType(variantContext, state, property);
  return IsLiteralNumber(canonicalAs) || IsLiteralString(canonicalAs) ? { [canonicalAs.const]: instantiatedProperty } : {};
}
function MappedProperties(context, state, identifier, variants, as, property) {
  return variants.reduce((result, left) => {
    return [...result, MappedVariant(context, state, identifier, left, as, property)];
  }, []);
}
function MappedObjects(properties) {
  return properties.reduce((result, left) => {
    return [...result, _Object_(left)];
  }, []);
}
function MappedOperation(context, state, identifier, type, as, property) {
  const variants = MappedVariants(type);
  const mappedProperties = MappedProperties(context, state, identifier, variants, as, property);
  const mappedObjects = MappedObjects(mappedProperties);
  const result = EvaluateIntersect(mappedObjects);
  return result;
}

// node_modules/typebox/build/type/engine/mapped/instantiate.mjs
function MappedAction(context, state, identifier, type, as, property, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(MappedOperation(context, state, identifier, type, as, property), {}, options) : MappedDeferred(identifier, type, as, property, options);
  return result;
}
function MappedInstantiate(context, state, identifier, type, as, property, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return MappedAction(context, state, identifier, instantiatedType, as, property, options);
}

// node_modules/typebox/build/type/engine/module/instantiate.mjs
function InstantiateCyclics(context, declarations, cyclicKeys) {
  const declarationContext = memory_exports.Assign(context, declarations);
  const declarationKeys = guard_exports.Keys(declarations).filter((key) => cyclicKeys.includes(key));
  return declarationKeys.reduce((result, key) => {
    return { ...result, [key]: InstantiateCyclic(declarationContext, key, declarations[key]) };
  }, {});
}
function InstantiateNonCyclics(context, declarations, cyclicKeys) {
  const declarationContext = memory_exports.Assign(context, declarations);
  const declarationKeys = guard_exports.Keys(declarations).filter((key) => !cyclicKeys.includes(key));
  return declarationKeys.reduce((result, key) => {
    return { ...result, [key]: InstantiateType(declarationContext, State([], []), declarations[key]) };
  }, {});
}
function InstantiateModule(context, declarations, options) {
  const cyclicCandidates = CyclicCandidates(declarations);
  const instantiatedCyclics = InstantiateCyclics(context, declarations, cyclicCandidates);
  const instantiatedNonCyclics = InstantiateNonCyclics(context, declarations, cyclicCandidates);
  const instantiatedModule = { ...instantiatedCyclics, ...instantiatedNonCyclics };
  return memory_exports.Update(instantiatedModule, {}, options);
}
function ModuleInstantiate(context, _state, declarations, options) {
  const instantiatedModule = InstantiateModule(context, declarations, options);
  return instantiatedModule;
}

// node_modules/typebox/build/type/action/non_nullable.mjs
function NonNullableDeferred(type, options = {}) {
  return Deferred("NonNullable", [type], options);
}
function NonNullable(type, options = {}) {
  return NonNullableAction(type, options);
}

// node_modules/typebox/build/type/engine/non_nullable/instantiate.mjs
function NonNullableOperation(type) {
  const excluded = Union([Null(), Undefined()]);
  return ExcludeAction(type, excluded, {});
}
function NonNullableAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(NonNullableOperation(type), {}, options) : NonNullableDeferred(type, options);
  return result;
}
function NonNullableInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return NonNullableAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/omit.mjs
function OmitDeferred(type, indexer, options = {}) {
  return Deferred("Omit", [type, indexer], options);
}
function Omit(type, indexer_or_keys, options = {}) {
  const indexer = guard_exports.IsArray(indexer_or_keys) ? KeysToIndexer(indexer_or_keys) : indexer_or_keys;
  return OmitAction(type, indexer, options);
}

// node_modules/typebox/build/type/engine/indexable/to_indexable.mjs
function ToIndexable(type) {
  const collapsed = CollapseToObject(type);
  const result = IsObject2(collapsed) ? collapsed.properties : Unreachable();
  return result;
}

// node_modules/typebox/build/type/engine/omit/from_type.mjs
function FromKeys(properties, keys) {
  const result = guard_exports.Keys(properties).reduce((result2, key) => {
    return keys.includes(key) ? result2 : { ...result2, [key]: properties[key] };
  }, {});
  return result;
}
function FromType14(type, indexer) {
  const indexable = ToIndexable(type);
  const indexableKeys = ToIndexableKeys(indexer);
  const omitted = FromKeys(indexable, indexableKeys);
  const result = _Object_(omitted);
  return result;
}

// node_modules/typebox/build/type/engine/omit/instantiate.mjs
function OmitAction(type, indexer, options) {
  const result = CanInstantiate([type, indexer]) ? memory_exports.Update(FromType14(type, indexer), {}, options) : OmitDeferred(type, indexer, options);
  return result;
}
function OmitInstantiate(context, state, type, indexer, options) {
  const instantiatedType = InstantiateType(context, state, type);
  const instantiatedIndexer = InstantiateType(context, state, indexer);
  return OmitAction(instantiatedType, instantiatedIndexer, options);
}

// node_modules/typebox/build/type/action/parameters.mjs
function ParametersDeferred(type, options = {}) {
  return Deferred("Parameters", [type], options);
}
function Parameters(type, options = {}) {
  return ParametersAction(type, options);
}

// node_modules/typebox/build/type/engine/parameters/instantiate.mjs
function ParametersOperation(type) {
  const parameters = IsFunction2(type) ? type["parameters"] : [];
  const instantiatedParameters = InstantiateElements({}, State([], []), parameters);
  const result = Tuple(instantiatedParameters);
  return result;
}
function ParametersAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(ParametersOperation(type), {}, options) : ParametersDeferred(type, options);
  return result;
}
function ParametersInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return ParametersAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/partial.mjs
function PartialDeferred(type, options = {}) {
  return Deferred("Partial", [type], options);
}
function Partial(type, options = {}) {
  return PartialAction(type, options);
}

// node_modules/typebox/build/type/engine/partial/from_cyclic.mjs
function FromCyclic3(defs, ref) {
  const target = CyclicTarget(defs, ref);
  const partial = FromType15(target);
  const result = Cyclic(memory_exports.Assign(defs, { [ref]: partial }), ref);
  return result;
}

// node_modules/typebox/build/type/engine/partial/from_dependent.mjs
function FromDependent3(if_, then_, else_) {
  const evaluated = EvaluateDependent(if_, then_, else_);
  const result = FromType15(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/partial/from_intersect.mjs
function FromIntersect3(types2) {
  const evaluated = EvaluateIntersect(types2);
  const result = FromType15(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/partial/from_union.mjs
function FromUnion6(types2) {
  const result = types2.map((type) => FromType15(type));
  return Union(result);
}

// node_modules/typebox/build/type/engine/partial/from_object.mjs
function FromObject6(properties) {
  const mapped = guard_exports.Keys(properties).reduce((result2, left) => {
    return { ...result2, [left]: AddOptional(properties[left]) };
  }, {});
  const result = _Object_(mapped);
  return result;
}

// node_modules/typebox/build/type/engine/partial/from_type.mjs
function FromType15(type) {
  return IsCyclic(type) ? FromCyclic3(type.$defs, type.$ref) : IsDependent(type) ? FromDependent3(type.if, type.then, type.else) : IsIntersect(type) ? FromIntersect3(type.allOf) : IsUnion(type) ? FromUnion6(type.anyOf) : IsObject2(type) ? FromObject6(type.properties) : _Object_({});
}

// node_modules/typebox/build/type/engine/partial/instantiate.mjs
function PartialAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType15(type), {}, options) : PartialDeferred(type, options);
  return result;
}
function PartialInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return PartialAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/pick.mjs
function PickDeferred(type, indexer, options = {}) {
  return Deferred("Pick", [type, indexer], options);
}
function Pick(type, indexer_or_keys, options = {}) {
  const indexer = guard_exports.IsArray(indexer_or_keys) ? KeysToIndexer(indexer_or_keys) : indexer_or_keys;
  return PickAction(type, indexer, options);
}

// node_modules/typebox/build/type/engine/pick/from_type.mjs
function FromKeys2(properties, keys) {
  const result = guard_exports.Keys(properties).reduce((result2, key) => {
    return keys.includes(key) ? memory_exports.Assign(result2, { [key]: properties[key] }) : result2;
  }, {});
  return result;
}
function FromType16(type, indexer) {
  const indexable = ToIndexable(type);
  const keys = ToIndexableKeys(indexer);
  const applied = FromKeys2(indexable, keys);
  const result = _Object_(applied);
  return result;
}

// node_modules/typebox/build/type/engine/pick/instantiate.mjs
function PickAction(type, indexer, options) {
  const result = CanInstantiate([type, indexer]) ? memory_exports.Update(FromType16(type, indexer), {}, options) : PickDeferred(type, indexer, options);
  return result;
}
function PickInstantiate(context, state, type, indexer, options) {
  const instantiatedType = InstantiateType(context, state, type);
  const instantiatedIndexer = InstantiateType(context, state, indexer);
  return PickAction(instantiatedType, instantiatedIndexer, options);
}

// node_modules/typebox/build/type/action/readonly_object.mjs
function ReadonlyObjectDeferred(type, options = {}) {
  return Deferred("ReadonlyObject", [type], options);
}
function ReadonlyObject(type, options = {}) {
  return ReadonlyObjectAction(type, options);
}
var ReadonlyType = ReadonlyObject;

// node_modules/typebox/build/type/engine/readonly_object/from_array.mjs
function FromArray4(type) {
  const result = AddImmutable(_Array_(type));
  return result;
}

// node_modules/typebox/build/type/engine/readonly_object/from_cyclic.mjs
function FromCyclic4(defs, ref) {
  const target = CyclicTarget(defs, ref);
  const partial = FromType17(target);
  const result = Cyclic(memory_exports.Assign(defs, { [ref]: partial }), ref);
  return result;
}

// node_modules/typebox/build/type/engine/readonly_object/from_dependent.mjs
function FromDependent4(if_, then_, else_) {
  const evaluated = EvaluateDependent(if_, then_, else_);
  const result = FromType17(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/readonly_object/from_intersect.mjs
function FromIntersect4(types2) {
  const evaluated = EvaluateIntersect(types2);
  const result = FromType17(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/readonly_object/from_object.mjs
function FromObject7(properties) {
  const mapped = guard_exports.Keys(properties).reduce((result2, left) => {
    return { ...result2, [left]: AddReadonly(properties[left]) };
  }, {});
  const result = _Object_(mapped);
  return result;
}

// node_modules/typebox/build/type/engine/readonly_object/from_tuple.mjs
function FromTuple4(types2) {
  const result = AddImmutable(Tuple(types2));
  return result;
}

// node_modules/typebox/build/type/engine/readonly_object/from_union.mjs
function FromUnion7(types2) {
  const result = types2.map((type) => FromType17(type));
  return Union(result);
}

// node_modules/typebox/build/type/engine/readonly_object/from_type.mjs
function FromType17(type) {
  return IsArray2(type) ? FromArray4(type.items) : IsCyclic(type) ? FromCyclic4(type.$defs, type.$ref) : IsDependent(type) ? FromDependent4(type.if, type.then, type.else) : IsIntersect(type) ? FromIntersect4(type.allOf) : IsObject2(type) ? FromObject7(type.properties) : IsTuple(type) ? FromTuple4(type.items) : IsUnion(type) ? FromUnion7(type.anyOf) : type;
}

// node_modules/typebox/build/type/engine/readonly_object/instantiate.mjs
function ReadonlyObjectAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType17(type), {}, options) : ReadonlyObjectDeferred(type);
  return result;
}
function ReadonlyObjectInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return ReadonlyObjectAction(instantiatedType, options);
}

// node_modules/typebox/build/type/engine/ref/instantiate.mjs
function RefInstantiate(context, state, type, ref) {
  return state.visited.includes(ref) ? type : ref in context ? InstantiateType(context, State(state["callstack"], [...state["visited"], ref]), context[ref]) : type;
}

// node_modules/typebox/build/type/engine/required/from_cyclic.mjs
function FromCyclic5(defs, ref) {
  const target = CyclicTarget(defs, ref);
  const partial = FromType18(target);
  const result = Cyclic(memory_exports.Assign(defs, { [ref]: partial }), ref);
  return result;
}

// node_modules/typebox/build/type/engine/required/from_dependent.mjs
function FromDependent5(if_, then_, else_) {
  const evaluated = EvaluateDependent(if_, then_, else_);
  const result = FromType18(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/required/from_intersect.mjs
function FromIntersect5(types2) {
  const evaluated = EvaluateIntersect(types2);
  const result = FromType18(evaluated);
  return result;
}

// node_modules/typebox/build/type/engine/required/from_union.mjs
function FromUnion8(types2) {
  const result = types2.map((type) => FromType18(type));
  return Union(result);
}

// node_modules/typebox/build/type/engine/required/from_object.mjs
function FromObject8(properties) {
  const mapped = guard_exports.Keys(properties).reduce((result2, left) => {
    return { ...result2, [left]: RemoveOptional(properties[left]) };
  }, {});
  const result = _Object_(mapped);
  return result;
}

// node_modules/typebox/build/type/engine/required/from_type.mjs
function FromType18(type) {
  return IsCyclic(type) ? FromCyclic5(type.$defs, type.$ref) : IsDependent(type) ? FromDependent5(type.if, type.then, type.else) : IsIntersect(type) ? FromIntersect5(type.allOf) : IsUnion(type) ? FromUnion8(type.anyOf) : IsObject2(type) ? FromObject8(type.properties) : _Object_({});
}

// node_modules/typebox/build/type/action/required.mjs
function RequiredDeferred(type, options = {}) {
  return Deferred("Required", [type], options);
}
function Required(type, options = {}) {
  return RequiredAction(type, options);
}

// node_modules/typebox/build/type/engine/required/instantiate.mjs
function RequiredAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(FromType18(type), {}, options) : RequiredDeferred(type, options);
  return result;
}
function RequiredInstantiate(context, state, type, options) {
  const instaniatedType = InstantiateType(context, state, type);
  return RequiredAction(instaniatedType, options);
}

// node_modules/typebox/build/type/action/return_type.mjs
function ReturnTypeDeferred(type, options = {}) {
  return Deferred("ReturnType", [type], options);
}
function ReturnType(type, options = {}) {
  return ReturnTypeAction(type, options);
}

// node_modules/typebox/build/type/engine/return_type/instantiate.mjs
function ReturnTypeOperation(type) {
  return IsFunction2(type) ? type["returnType"] : Never();
}
function ReturnTypeAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(ReturnTypeOperation(type), {}, options) : ReturnTypeDeferred(type, options);
  return result;
}
function ReturnTypeInstantiate(context, state, type, options = {}) {
  const instantiatedType = InstantiateType(context, state, type);
  return ReturnTypeAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/with.mjs
function WithDeferred(type, options) {
  return Deferred("With", [type, options], {});
}
function With2(type, options) {
  return WithAction(type, options);
}

// node_modules/typebox/build/type/engine/with/instantiate.mjs
function WithAction(type, options) {
  const result = CanInstantiate([type]) ? memory_exports.Update(type, {}, options) : WithDeferred(type, options);
  return result;
}
function WithInstantiate(context, state, type, options) {
  const instaniatedType = InstantiateType(context, state, type);
  return WithAction(instaniatedType, options);
}

// node_modules/typebox/build/type/engine/rest/spread.mjs
function SpreadElement(type) {
  const result = IsRest(type) ? IsTuple(type.items) ? RestSpread(type.items.items) : IsInfer(type.items) ? [type] : IsRef(type.items) ? [type] : [Never()] : [type];
  return result;
}
function RestSpread(types2) {
  const result = types2.reduce((result2, left) => {
    return [...result2, ...SpreadElement(left)];
  }, []);
  return result;
}

// node_modules/typebox/build/type/engine/instantiate.mjs
function State(callstack, visited) {
  return { callstack, visited };
}
function CanInstantiate(types2) {
  return guard_exports.ShiftLeft(types2, (left, right) => IsRef(left) ? false : CanInstantiate(right), () => true);
}
function InstantiateProperties(context, state, properties) {
  return guard_exports.Keys(properties).reduce((result, key) => {
    return { ...result, [key]: InstantiateType(context, state, properties[key]) };
  }, {});
}
function InstantiateElements(context, state, types2) {
  const elements = InstantiateTypes(context, state, types2);
  const result = RestSpread(elements);
  return result;
}
function InstantiateTypes(context, state, types2) {
  return types2.map((type) => InstantiateType(context, state, type));
}
function WithModifiers(type, instantiatedType) {
  const withOptional = IsOptional(type) ? AddOptionalAction(instantiatedType, {}) : instantiatedType;
  const withReadonly = IsReadonly(type) ? AddReadonlyAction(withOptional, {}) : withOptional;
  const withImmutable = IsImmutable(type) ? AddImmutableAction(withReadonly, {}) : withReadonly;
  return withImmutable;
}
function InstantiateDeferred(context, state, action, parameters, options) {
  return (
    // Modifiers
    guard_exports.IsEqual(action, "AddImmutable") ? AddImmutableInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "RemoveImmutable") ? RemoveImmutableInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "AddReadonly") ? AddReadonlyInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "RemoveReadonly") ? RemoveReadonlyInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "AddOptional") ? AddOptionalInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "RemoveOptional") ? RemoveOptionalInstantiate(context, state, parameters[0], options) : (
      // Actions
      guard_exports.IsEqual(action, "Capitalize") ? CapitalizeInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Conditional") ? ConditionalInstantiate(context, state, parameters[0], parameters[1], parameters[2], parameters[3], options) : guard_exports.IsEqual(action, "ConstructorParameters") ? ConstructorParametersInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Evaluate") ? EvaluateInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Exclude") ? ExcludeInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "Extract") ? ExtractInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "Index") ? IndexInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "InstanceType") ? InstanceTypeInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Interface") ? InterfaceInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "KeyOf") ? KeyOfInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Lowercase") ? LowercaseInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Mapped") ? MappedInstantiate(context, state, parameters[0], parameters[1], parameters[2], parameters[3], options) : guard_exports.IsEqual(action, "Module") ? ModuleInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "NonNullable") ? NonNullableInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Pick") ? PickInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "Parameters") ? ParametersInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Partial") ? PartialInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Omit") ? OmitInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "ReadonlyObject") ? ReadonlyObjectInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Record") ? RecordInstantiate(context, state, parameters[0], parameters[1], options) : guard_exports.IsEqual(action, "Required") ? RequiredInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "ReturnType") ? ReturnTypeInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "TemplateLiteral") ? TemplateLiteralInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Uncapitalize") ? UncapitalizeInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "Uppercase") ? UppercaseInstantiate(context, state, parameters[0], options) : guard_exports.IsEqual(action, "With") ? WithInstantiate(context, state, parameters[0], parameters[1]) : Deferred(action, parameters, options)
    )
  );
}
function InstantiateImmediate(context, state, type) {
  const instantiatedType = IsRef(type) ? RefInstantiate(context, state, type, type.$ref) : IsArray2(type) ? _Array_(InstantiateType(context, state, type.items), ArrayOptions(type)) : IsCall(type) ? CallInstantiate(context, state, type.target, type.arguments) : IsConstructor2(type) ? Constructor(InstantiateTypes(context, state, type.parameters), InstantiateType(context, state, type.instanceType), ConstructorOptions(type)) : IsFunction2(type) ? _Function_(InstantiateTypes(context, state, type.parameters), InstantiateType(context, state, type.returnType), FunctionOptions(type)) : IsDependent(type) ? Dependent(InstantiateType(context, state, type.if), InstantiateType(context, state, type.then), InstantiateType(context, state, type.else), DependentOptions(type)) : IsIntersect(type) ? Intersect(InstantiateTypes(context, state, type.allOf), IntersectOptions(type)) : IsObject2(type) ? _Object_(InstantiateProperties(context, state, type.properties), ObjectOptions(type)) : IsRecord(type) ? RecordFromPattern(RecordPattern(type), InstantiateType(context, state, RecordValue(type))) : IsRest(type) ? Rest(InstantiateType(context, state, type.items)) : IsTuple(type) ? Tuple(InstantiateElements(context, state, type.items), TupleOptions(type)) : IsUnion(type) ? Union(InstantiateTypes(context, state, type.anyOf), UnionOptions(type)) : type;
  const withModifiers = WithModifiers(type, instantiatedType);
  return withModifiers;
}
function InstantiateType(context, state, type) {
  const result = IsDeferred(type) ? InstantiateDeferred(context, state, type.action, type.parameters, type.options) : InstantiateImmediate(context, state, type);
  return result;
}
function Instantiate(context, type) {
  return InstantiateType(context, State([], []), type);
}

// node_modules/typebox/build/type/engine/immutable/instantiate_add.mjs
function AddImmutableOperation(type) {
  return memory_exports.Update(type, { "~immutable": true }, {});
}
function AddImmutableAction(type, options) {
  const result = memory_exports.Update(AddImmutableOperation(type), {}, options);
  return result;
}
function AddImmutableInstantiate(context, state, type, options) {
  const instantiatedType = InstantiateType(context, state, type);
  return AddImmutableAction(instantiatedType, options);
}

// node_modules/typebox/build/type/action/_add_immutable.mjs
function AddImmutableDeferred(type, options = {}) {
  return Deferred("AddImmutable", [type], options);
}
function AddImmutable(type, options = {}) {
  return AddImmutableAction(type, options);
}

// node_modules/typebox/build/type/action/evaluate.mjs
function EvaluateDeferred(type, options = {}) {
  return Deferred("Evaluate", [type], options);
}
function Evaluate(type, options = {}) {
  return EvaluateAction(type, options);
}

// node_modules/typebox/build/type/action/module.mjs
function ModuleDeferred(declarations, options = {}) {
  return Deferred("Module", [declarations], options);
}
function Module2(declarations, options = {}) {
  return ModuleInstantiate({}, State([], []), declarations, options);
}

// node_modules/typebox/build/type/script/script.mjs
function Script2(...args) {
  const [context, input, options] = arguments_exports.Match(args, {
    2: (script, options2) => guard_exports.IsString(script) ? [{}, script, options2] : [script, options2, {}],
    3: (context2, script, options2) => [context2, script, options2],
    1: (script) => [{}, script, {}]
  });
  const result = Script(input);
  const parsed = guard_exports.IsArray(result) && guard_exports.IsEqual(result.length, 2) ? InstantiateType(context, State([], []), result[0]) : Never();
  return memory_exports.Update(parsed, {}, options);
}

// node_modules/typebox/build/typebox.mjs
var typebox_exports = {};
__export(typebox_exports, {
  Any: () => Any,
  Array: () => _Array_,
  BigInt: () => BigInt2,
  Boolean: () => Boolean2,
  Call: () => Call,
  Capitalize: () => Capitalize,
  Codec: () => Codec,
  Conditional: () => Conditional,
  Constructor: () => Constructor,
  ConstructorParameters: () => ConstructorParameters,
  Cyclic: () => Cyclic,
  Decode: () => Decode,
  DecodeBuilder: () => DecodeBuilder,
  Dependent: () => Dependent,
  Encode: () => Encode,
  EncodeBuilder: () => EncodeBuilder,
  Enum: () => Enum,
  Evaluate: () => Evaluate,
  Exclude: () => Exclude,
  Extends: () => Extends,
  ExtendsResult: () => result_exports,
  Extract: () => Extract,
  Function: () => _Function_,
  Generic: () => Generic,
  Identifier: () => Identifier,
  Immutable: () => Immutable,
  Index: () => Index,
  Infer: () => Infer,
  InstanceType: () => InstanceType,
  Instantiate: () => Instantiate,
  Integer: () => Integer,
  Interface: () => Interface,
  Intersect: () => Intersect,
  IsAny: () => IsAny,
  IsArray: () => IsArray2,
  IsBigInt: () => IsBigInt2,
  IsBoolean: () => IsBoolean3,
  IsCall: () => IsCall,
  IsCodec: () => IsCodec,
  IsConstructor: () => IsConstructor2,
  IsCyclic: () => IsCyclic,
  IsDependent: () => IsDependent,
  IsEnum: () => IsEnum,
  IsEnumValue: () => IsEnumValue,
  IsFunction: () => IsFunction2,
  IsGeneric: () => IsGeneric,
  IsIdentifier: () => IsIdentifier,
  IsImmutable: () => IsImmutable,
  IsInfer: () => IsInfer,
  IsInteger: () => IsInteger2,
  IsIntersect: () => IsIntersect,
  IsKind: () => IsKind,
  IsLiteral: () => IsLiteral,
  IsNever: () => IsNever,
  IsNull: () => IsNull2,
  IsNumber: () => IsNumber3,
  IsObject: () => IsObject2,
  IsOptional: () => IsOptional,
  IsParameter: () => IsParameter,
  IsReadonly: () => IsReadonly,
  IsRecord: () => IsRecord,
  IsRef: () => IsRef,
  IsRefine: () => IsRefine,
  IsRest: () => IsRest,
  IsSchema: () => IsSchema,
  IsString: () => IsString3,
  IsSymbol: () => IsSymbol2,
  IsTemplateLiteral: () => IsTemplateLiteral,
  IsThis: () => IsThis,
  IsTuple: () => IsTuple,
  IsUndefined: () => IsUndefined2,
  IsUnion: () => IsUnion,
  IsUnknown: () => IsUnknown,
  IsUnsafe: () => IsUnsafe,
  IsVoid: () => IsVoid,
  KeyOf: () => KeyOf2,
  Literal: () => Literal,
  Lowercase: () => Lowercase,
  Mapped: () => Mapped,
  Module: () => Module2,
  Never: () => Never,
  NonNullable: () => NonNullable,
  Null: () => Null,
  Number: () => Number2,
  Object: () => _Object_,
  Omit: () => Omit,
  Optional: () => Optional,
  Parameter: () => Parameter,
  Parameters: () => Parameters,
  Partial: () => Partial,
  Pick: () => Pick,
  Readonly: () => Readonly,
  ReadonlyObject: () => ReadonlyObject,
  ReadonlyType: () => ReadonlyType,
  Record: () => Record,
  RecordKey: () => RecordKey,
  RecordPattern: () => RecordPattern,
  RecordValue: () => RecordValue,
  Ref: () => Ref,
  Refine: () => Refine,
  Required: () => Required,
  Rest: () => Rest,
  ReturnType: () => ReturnType,
  Script: () => Script2,
  String: () => String2,
  Symbol: () => Symbol2,
  TemplateLiteral: () => TemplateLiteral2,
  This: () => This,
  Tuple: () => Tuple,
  Uncapitalize: () => Uncapitalize,
  Undefined: () => Undefined,
  Union: () => Union,
  Unknown: () => Unknown,
  Unsafe: () => Unsafe,
  Uppercase: () => Uppercase,
  Void: () => Void,
  With: () => With2
});

// packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts
import * as path16 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
import * as fs11 from "node:fs";
import * as path15 from "node:path";

// packages/coding-agent/src/utils/shell.ts
import { existsSync as existsSync2 } from "node:fs";
import * as path from "node:path";
import { delimiter } from "node:path";
import { spawn, spawnSync } from "child_process";

// packages/coding-agent/src/config.ts
import { accessSync, constants, existsSync, readFileSync, realpathSync as realpathSync2 } from "fs";
import { basename, dirname, join as join2, resolve, sep as sep2, win32 } from "path";
import { fileURLToPath as fileURLToPath2 } from "url";

// packages/coding-agent/src/utils/child-process.ts
var import_cross_spawn = __toESM(require_cross_spawn(), 1);
import {
  spawn as nodeSpawn,
  spawnSync as nodeSpawnSync
} from "node:child_process";

// packages/coding-agent/src/utils/paths.ts
import { realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve as nodeResolvePath, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
var UNICODE_SPACES = /[\u00A0\u2000-\u200A\u202F\u205F\u3000]/g;
function normalizePath(input, options = {}) {
  let normalized = options.trim ? input.trim() : input;
  if (options.normalizeUnicodeSpaces) {
    normalized = normalized.replace(UNICODE_SPACES, " ");
  }
  if (options.stripAtPrefix && normalized.startsWith("@")) {
    normalized = normalized.slice(1);
  }
  if (options.expandTilde ?? true) {
    const home = options.homeDir ?? homedir();
    if (normalized === "~") return home;
    if (normalized.startsWith("~/") || process.platform === "win32" && normalized.startsWith("~\\")) {
      return join(home, normalized.slice(2));
    }
  }
  if (/^file:\/\//.test(normalized)) {
    return fileURLToPath(normalized);
  }
  return normalized;
}

// packages/coding-agent/src/config.ts
var __filename = fileURLToPath2(import.meta.url);
var __dirname = dirname(__filename);
var isBunBinary = import.meta.url.includes("$bunfs") || import.meta.url.includes("~BUN") || import.meta.url.includes("%7EBUN");
var isBunRuntime = !!process.versions.bun;
function getPackageDir() {
  const envDir = process.env.PI_PACKAGE_DIR;
  if (envDir) {
    return normalizePath(envDir);
  }
  if (isBunBinary) {
    return dirname(process.execPath);
  }
  let dir = __dirname;
  while (dir !== dirname(dir)) {
    if (existsSync(join2(dir, "package.json"))) {
      return dir;
    }
    dir = dirname(dir);
  }
  return __dirname;
}
function getPackageJsonPath() {
  return join2(getPackageDir(), "package.json");
}
var pkg = {};
try {
  pkg = JSON.parse(readFileSync(getPackageJsonPath(), "utf-8"));
} catch (e) {
  const err = e;
  if (err.code !== "ENOENT") throw e;
}
var piConfigName = pkg.piConfig?.name;
var PACKAGE_NAME = pkg.name || "@earendil-works/pi-coding-agent";
var APP_NAME = piConfigName || "pi";
var CONFIG_DIR_NAME = pkg.piConfig?.configDir || ".pi";
var VERSION = pkg.version || "0.0.0";
var ENV_AGENT_DIR = `${APP_NAME.toUpperCase()}_CODING_AGENT_DIR`;
var ENV_SESSION_DIR = `${APP_NAME.toUpperCase()}_CODING_AGENT_SESSION_DIR`;

// packages/coding-agent/src/utils/shell.ts
var trackedDetachedChildPids = /* @__PURE__ */ new Set();
function killTrackedDetachedChildren() {
  for (const pid of trackedDetachedChildPids) {
    killProcessTree(pid);
  }
  trackedDetachedChildPids.clear();
}
function killProcessTree(pid) {
  if (process.platform === "win32") {
    try {
      spawn("taskkill", ["/F", "/T", "/PID", String(pid)], {
        stdio: "ignore",
        detached: true,
        windowsHide: true
      });
    } catch {
    }
  } else {
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      try {
        process.kill(pid, "SIGKILL");
      } catch {
      }
    }
  }
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/budget.ts
import * as fs from "node:fs";
import * as path2 from "node:path";
var WALL_GUARD_RATIO = 0.7;
var RAG_BUDGET_FILENAME = "rag-budget.json";
var RAG_HEARTBEAT_INTERVAL_MS = 3e4;
var BREAKER_KINDS = /* @__PURE__ */ new Set(["connect", "timeout", "protocol"]);
var BREAKER_THRESHOLD = 3;
function toNonNegativeInt(value) {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}
function readBudgetState(file) {
  let text;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch {
    return null;
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const record = parsed;
  const number = (key) => {
    const value = record[key];
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  };
  return {
    chatUsed: toNonNegativeInt(number("chatUsed")),
    chatBudget: toNonNegativeInt(number("chatBudget")),
    timeUsedMs: toNonNegativeInt(number("timeUsedMs")),
    timeBudgetMs: toNonNegativeInt(number("timeBudgetMs"))
  };
}
var Budget = class {
  constructor(workerTaskDir2, chatBudget, timeBudgetMs, opts = {}) {
    this.chatUsed = 0;
    this.timeUsedMs = 0;
    this.workerTaskDir = workerTaskDir2 !== null && workerTaskDir2.length > 0 ? workerTaskDir2 : null;
    this.chatBudget = toNonNegativeInt(chatBudget);
    this.timeBudgetMs = toNonNegativeInt(timeBudgetMs);
    this.taskWallMs = opts.taskWallMs ?? null;
    this.now = opts.now ?? Date.now;
    this.startedAt = this.now();
    this.load();
  }
  /** Seed counters from a previous run in the same task dir (read-only). */
  load() {
    const state = this.readExisting();
    if (state === null) return;
    this.chatUsed = state.chatUsed;
    this.timeUsedMs = state.timeUsedMs;
  }
  /**
   * Synchronous reservation: enforce the cumulative budget, then spend one
   * chat slot **before** any `await`. The count is persisted at once so a
   * crash mid-call still leaves the reservation behind.
   */
  reserveChat() {
    const cumulative = this.checkCumulative();
    if (!cumulative.ok) return cumulative;
    if (this.chatUsed >= this.chatBudget) {
      return {
        ok: false,
        kind: "budget",
        message: `rag chat budget exhausted (used=${this.chatUsed}, budget=${this.chatBudget})`
      };
    }
    this.chatUsed += 1;
    this.persist();
    return { ok: true };
  }
  /**
   * Settle a chat reservation. `ok=true` keeps the spent slot (the call was
   * made). On failure only a provably-undelivered `connect` (or an explicit
   * `null` release, used when the guard refuses before the request) refunds;
   * `timeout` may have been delivered and therefore never refunds.
   */
  settleChat(ok, kind) {
    if (ok) return;
    if (kind !== "connect" && kind !== null) return;
    if (this.chatUsed > 0) this.chatUsed -= 1;
    this.persist();
  }
  /** Charge the elapsed wall time of one logical call (success or failure). */
  accumulate(ms) {
    if (!Number.isFinite(ms) || ms <= 0) return;
    this.timeUsedMs += Math.round(ms);
    this.persist();
  }
  /** Task-level cumulative RAG time budget (VC-025). */
  checkCumulative() {
    if (this.timeUsedMs > this.timeBudgetMs) {
      return {
        ok: false,
        kind: "budget",
        message: `rag cumulative time budget exhausted (used=${this.timeUsedMs}ms, budget=${this.timeBudgetMs}ms)`
      };
    }
    return { ok: true };
  }
  /** Cheap retrieval is still allowed while the cumulative budget holds. */
  canCallCheap() {
    return this.checkCumulative().ok;
  }
  /** Wall-clock guard: past 70% of the task wall budget only cheap calls pass. */
  checkWall(nowMs) {
    const wall = this.taskWallMs;
    if (wall === null || !Number.isFinite(wall) || wall <= 0) return { ok: true };
    const elapsed = Math.max(0, nowMs - this.startedAt);
    if (elapsed > wall * WALL_GUARD_RATIO) {
      return {
        ok: false,
        kind: "budget",
        message: `rag wall clock guard: elapsed=${elapsed}ms exceeds ${Math.round(
          WALL_GUARD_RATIO * 100
        )}% of task wall budget ${wall}ms`
      };
    }
    return { ok: true };
  }
  state() {
    return {
      chatUsed: this.chatUsed,
      chatBudget: this.chatBudget,
      timeUsedMs: this.timeUsedMs,
      timeBudgetMs: this.timeBudgetMs
    };
  }
  /**
   * Rewrite `<workerTaskDir>/rag-budget.json` as a whole (read-modify-write).
   * No-op when there is no task dir (PM/non-worker session) — the file is
   * created on the first RAG call, never at activation (D-014).
   */
  persist() {
    const dir = this.workerTaskDir;
    if (dir === null) return;
    const existing = this.readExisting();
    if (existing !== null) {
      this.chatUsed = Math.max(this.chatUsed, existing.chatUsed);
      this.timeUsedMs = Math.max(this.timeUsedMs, existing.timeUsedMs);
    }
    const merged = {
      chatUsed: this.chatUsed,
      chatBudget: this.chatBudget,
      timeUsedMs: this.timeUsedMs,
      timeBudgetMs: this.timeBudgetMs
    };
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(this.filePath(), `${JSON.stringify(merged, null, 2)}
`, "utf8");
  }
  filePath() {
    return path2.join(this.workerTaskDir ?? "", RAG_BUDGET_FILENAME);
  }
  readExisting() {
    if (this.workerTaskDir === null) return null;
    return readBudgetState(this.filePath());
  }
};
var Breaker = class {
  constructor() {
    this.failures = /* @__PURE__ */ new Map();
  }
  noteFailure(server, kind) {
    if (!BREAKER_KINDS.has(kind)) return;
    this.failures.set(server, (this.failures.get(server) ?? 0) + 1);
  }
  isOpen(server) {
    return (this.failures.get(server) ?? 0) >= BREAKER_THRESHOLD;
  }
  noteSuccess(server) {
    this.failures.delete(server);
  }
};
function withHeartbeat(intervalMs, onUpdate, fn) {
  const period = Number.isFinite(intervalMs) && intervalMs > 0 ? intervalMs : RAG_HEARTBEAT_INTERVAL_MS;
  const startedAt = Date.now();
  const timer = setInterval(() => {
    if (onUpdate === void 0) return;
    const elapsedMs = Date.now() - startedAt;
    try {
      onUpdate(`rag call in progress (elapsed ${Math.round(elapsedMs / 1e3)}s)`);
    } catch {
    }
  }, period);
  return Promise.resolve().then(fn).finally(() => clearInterval(timer));
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts
var import_yaml2 = __toESM(require_dist(), 1);
import { createHash } from "node:crypto";
import * as fs3 from "node:fs";
import * as path4 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/shared/target-config.ts
var import_yaml = __toESM(require_dist(), 1);
import * as fs2 from "node:fs";
import * as path3 from "node:path";
var ENV_TARGET_GAME = "MW_TARGET_GAME";
var ENV_TARGET_ENGINE = "MW_TARGET_ENGINE";
var ENV_PARTITION_PARENT = "MW_PARTITION_PARENT";
var ENV_PARTITION_ROOT = "MW_PARTITION_ROOT";
var TargetConfigError = class extends Error {
  constructor(kind, message) {
    super(message);
    this.name = "TargetConfigError";
    this.kind = kind;
  }
};
var TARGET_YML = "target.yml";
function fail(kind, message) {
  throw new TargetConfigError(kind, message);
}
function requireString(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    fail("invalid-config", `target.yml: field '${field}' must be a non-empty string`);
  }
  return value;
}
function optionalString(value, field) {
  return value === void 0 || value === null ? null : requireString(value, field);
}
function stringArray(value, field) {
  if (value === void 0 || value === null) return [];
  if (!Array.isArray(value) || value.some((e) => typeof e !== "string" || e.trim() === "")) {
    fail("invalid-config", `target.yml: field '${field}' must be a list of non-empty strings`);
  }
  return value;
}
function normalizeRoot(raw, controlRoot) {
  const resolved = path3.resolve(controlRoot, raw);
  try {
    return fs2.realpathSync.native(resolved);
  } catch {
    let dir = resolved;
    const tail = [];
    for (; ; ) {
      const parent = path3.dirname(dir);
      if (parent === dir) return resolved;
      try {
        const real = fs2.realpathSync.native(dir);
        return tail.length === 0 ? real : path3.join(real, ...tail);
      } catch {
        tail.unshift(path3.basename(dir));
        dir = parent;
      }
    }
  }
}
function targetYmlPath(controlRoot) {
  return path3.join(controlRoot, ".agenticdoc", TARGET_YML);
}
function parseToolchain(value) {
  if (value === void 0 || value === null) return {};
  if (typeof value !== "object" || Array.isArray(value)) {
    fail("invalid-config", "target.yml: 'toolchain' must be a mapping of name to command");
  }
  const out = {};
  for (const [name, cmd] of Object.entries(value)) {
    if (typeof cmd !== "string" || cmd.trim() === "") {
      fail("invalid-config", `target.yml: toolchain.${name} must be a non-empty string`);
    }
    out[name] = cmd;
  }
  return out;
}
function parseIgnore(value) {
  if (value === void 0 || value === null) return { deny_globs: [] };
  if (typeof value !== "object" || Array.isArray(value)) {
    fail("invalid-config", "target.yml: 'ignore' must be a mapping");
  }
  const raw = value;
  return { deny_globs: stringArray(raw.deny_globs, "ignore.deny_globs") };
}
function parseContract(value) {
  if (value === void 0 || value === null) {
    return { forbidden_paths: [], conventions: null, docs: [] };
  }
  if (typeof value !== "object" || Array.isArray(value)) {
    fail("invalid-config", "target.yml: 'contract' must be a mapping");
  }
  const raw = value;
  const conventions = raw.conventions === void 0 || raw.conventions === null ? null : typeof raw.conventions === "string" ? raw.conventions : fail("invalid-config", "target.yml: contract.conventions must be a string");
  return {
    forbidden_paths: stringArray(raw.forbidden_paths, "contract.forbidden_paths"),
    conventions,
    docs: stringArray(raw.docs, "contract.docs")
  };
}
function rawTargetYml(controlRoot) {
  const file = targetYmlPath(controlRoot);
  let text;
  try {
    text = fs2.readFileSync(file, "utf-8");
  } catch {
    return {};
  }
  let parsed;
  try {
    parsed = (0, import_yaml.parse)(text);
  } catch (err) {
    fail(
      "invalid-yaml",
      `target.yml is not valid YAML (${targetYmlPath(controlRoot)}): ${err instanceof Error ? err.message : String(err)}`
    );
  }
  if (parsed === void 0 || parsed === null) {
    if (text.trim() === "" || text.replace(/^\uFEFF/, "").trim() === "") return {};
    fail("invalid-config", "target.yml: top level must be a mapping");
  }
  if (typeof parsed !== "object" || Array.isArray(parsed)) {
    fail("invalid-config", "target.yml: top level must be a mapping");
  }
  return parsed;
}
var V1_SHAPE_KEYS = ["mode", "game", "engine", "uproject"];
var V2_TOP_KEYS = /* @__PURE__ */ new Set(["active", "dual", "partition"]);
var DUAL_BLOCK_KEYS = /* @__PURE__ */ new Set(["game", "engine", "vcs", "uproject", "toolchain", "ignore", "contract"]);
var PARTITION_BLOCK_KEYS = /* @__PURE__ */ new Set(["parent", "partition", "vcs", "roots", "toolchain", "ignore", "contract"]);
var ROOTS_RESERVED = /* @__PURE__ */ new Set(["parent", "partition", "game", "engine", "uproject"]);
var ROOTS_NAME_RE = /^[A-Za-z0-9_-]+$/;
function detectShape(raw, fileExists) {
  if (!fileExists) return "none";
  if ("active" in raw) {
    const mixed = V1_SHAPE_KEYS.filter((k) => k in raw);
    if (mixed.length > 0) {
      fail(
        "invalid-config",
        `target.yml: mixed format \u2014 'active:' key (v2) together with v1 top-level field(s) ${mixed.join(
          ", "
        )}; use either v2 (active + mode blocks) or v1 (flat fields), not both`
      );
    }
    return "v2";
  }
  return "v1";
}
function decideActiveMode(input) {
  const ep = [];
  if (input.envPartitionParent !== null) ep.push(ENV_PARTITION_PARENT);
  if (input.envPartitionRoot !== null) ep.push(ENV_PARTITION_ROOT);
  const et = [];
  if (input.envTargetGame !== null) et.push(ENV_TARGET_GAME);
  if (input.envTargetEngine !== null) et.push(ENV_TARGET_ENGINE);
  if (input.fileShape === "v2") {
    const active = input.active;
    if (active === null || active !== "single" && active !== "dual" && active !== "partition") {
      fail(
        "invalid-config",
        `target.yml: 'active' must be one of 'single', 'dual', 'partition', got ${active === null ? "null" : `'${active}'`}`
      );
    }
    if (active === "dual" && ep.length > 0) {
      fail(
        "invalid-config",
        `cross env: ${ep.join(", ")} must not be set when active is 'dual' (dual mode uses MW_TARGET_GAME/MW_TARGET_ENGINE)`
      );
    }
    if (active === "partition" && et.length > 0) {
      fail(
        "invalid-config",
        `cross env: ${et.join(", ")} must not be set when active is 'partition' (partition mode uses MW_PARTITION_PARENT/MW_PARTITION_ROOT)`
      );
    }
    if (active === "single" && ep.length + et.length > 0) {
      fail("invalid-config", `cross env: ${[...ep, ...et].join(", ")} must not be set when active is 'single'`);
    }
    if (active === "single") return { mode: "single", block: null };
    return { mode: active, block: active };
  }
  if (input.fileShape === "v1") {
    if (ep.length > 0) {
      fail(
        "invalid-config",
        `cross env: ${ep.join(", ")} requires a v2 target.yml with 'active: partition' (v1 format has no partition mode)`
      );
    }
    return { mode: "legacy", block: null };
  }
  if (ep.length > 0 && et.length > 0) {
    fail(
      "invalid-config",
      `cross env: ${ep.join(", ")} and ${et.join(", ")} are mutually exclusive (partition env vs dual env); set only one family`
    );
  }
  if (ep.length === 2) return { mode: "partition", block: null };
  if (ep.length === 1) {
    const missing = input.envPartitionRoot === null ? ENV_PARTITION_ROOT : ENV_PARTITION_PARENT;
    fail(
      "invalid-config",
      `incomplete partition env activation: ${missing} is not set (partition env requires both MW_PARTITION_PARENT and MW_PARTITION_ROOT)`
    );
  }
  return { mode: "legacy", block: null };
}
function checkV2TopWhitelist(raw) {
  const extra = Object.keys(raw).filter((k) => !V2_TOP_KEYS.has(k));
  if (extra.length > 0) {
    fail(
      "invalid-config",
      `target.yml: unexpected top-level key(s) in v2 format: ${extra.join(", ")} (allowed: active, dual, partition)`
    );
  }
}
function v2Block(raw, name) {
  if (!(name in raw) || raw[name] === null || raw[name] === void 0) {
    fail("invalid-config", `target.yml: active '${name}' but the '${name}' block is missing`);
  }
  const block = raw[name];
  if (typeof block !== "object" || Array.isArray(block)) {
    fail("invalid-config", `target.yml: the '${name}' block must be a mapping`);
  }
  return block;
}
function checkBlockKeys(block, name, allowed) {
  const extra = Object.keys(block).filter((k) => !allowed.has(k));
  if (extra.length > 0) {
    fail("invalid-config", `target.yml: unexpected key(s) in the '${name}' block: ${extra.join(", ")}`);
  }
}
function checkRootsKeyTypes(rootsAst) {
  for (const pair of rootsAst.items) {
    if (!(0, import_yaml.isScalar)(pair.key) || typeof pair.key.value !== "string") {
      fail("invalid-config", "target.yml: roots keys must be strings");
    }
  }
}
function readRootsAst(controlRoot) {
  const file = targetYmlPath(controlRoot);
  let text;
  try {
    text = fs2.readFileSync(file, "utf-8");
  } catch {
    return null;
  }
  const node = (0, import_yaml.parseDocument)(text).getIn(["partition", "roots"], true);
  return (0, import_yaml.isMap)(node) ? node : null;
}
function parseRoots(value, controlRoot, rootsAst) {
  if (value === void 0 || value === null) return {};
  if (typeof value !== "object" || Array.isArray(value)) {
    fail("invalid-config", "target.yml: partition field 'roots' must be a mapping of name to path");
  }
  if (rootsAst !== null) checkRootsKeyTypes(rootsAst);
  const out = {};
  for (const [name, rawPath] of Object.entries(value)) {
    if (name === "" || !ROOTS_NAME_RE.test(name) || ROOTS_RESERVED.has(name)) {
      fail(
        "invalid-config",
        `target.yml: roots key '${name}' is invalid (must match [A-Za-z0-9_-]+ and must not be a reserved name: parent, partition, game, engine, uproject)`
      );
    }
    if (typeof rawPath !== "string" || rawPath.trim() === "") {
      fail("invalid-config", `target.yml: roots.${name} must be a non-empty string`);
    }
    out[name] = normalizeRoot(rawPath, controlRoot);
  }
  return out;
}
function relationNorm(p) {
  const normalized = path3.normalize(p);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}
function checkRootRelation(parentRoot, partitionRoot) {
  const a = relationNorm(parentRoot);
  const b = relationNorm(partitionRoot);
  if (a === b || a.startsWith(b + path3.sep) || b.startsWith(a + path3.sep)) {
    fail(
      "invalid-config",
      `target.yml: partition root relation is invalid \u2014 parent (${parentRoot}) and partition (${partitionRoot}) must not be equal or nested`
    );
  }
}
function loadPartitionConfig(controlRoot, controlNorm, block, envParent, envPartition, rootsAst) {
  let parentRaw = block === null ? null : block.parent;
  let partitionRaw = block === null ? null : block.partition;
  if (envParent !== null) parentRaw = envParent;
  if (envPartition !== null) partitionRaw = envPartition;
  if (parentRaw === null || parentRaw === void 0) {
    fail(
      "invalid-config",
      "target.yml: partition mode requires field 'parent' (partition block or env MW_PARTITION_PARENT)"
    );
  }
  if (partitionRaw === null || partitionRaw === void 0) {
    fail(
      "invalid-config",
      "target.yml: partition mode requires field 'partition' (partition block or env MW_PARTITION_ROOT)"
    );
  }
  const parent = requireString(parentRaw, "parent");
  const partition = requireString(partitionRaw, "partition");
  const parentRoot = normalizeRoot(parent, controlRoot);
  const partitionRoot = normalizeRoot(partition, controlRoot);
  const roots = parseRoots(block === null ? null : block.roots, controlRoot, rootsAst);
  checkRootRelation(parentRoot, partitionRoot);
  return {
    mode: "partition",
    controlRoot: controlNorm,
    gameRoot: null,
    engineRoot: null,
    parentRoot,
    partitionRoot,
    roots,
    vcs: optionalString(block === null ? null : block.vcs, "vcs"),
    uproject: null,
    toolchain: parseToolchain(block === null ? null : block.toolchain),
    ignore: parseIgnore(block === null ? null : block.ignore),
    contract: parseContract(block === null ? null : block.contract),
    source: envParent !== null || envPartition !== null ? "env" : "target-yml"
  };
}
function resolveLegacyConfig(controlRoot, raw, envGame, envEngine) {
  const fileMode = raw.mode === void 0 ? null : requireString(raw.mode, "mode");
  if (fileMode !== null && fileMode !== "dual" && fileMode !== "single") {
    fail("invalid-config", `target.yml: 'mode' must be 'dual' or 'single', got '${fileMode}'`);
  }
  const fileGame = optionalString(raw.game, "game");
  const fileEngine = optionalString(raw.engine, "engine");
  const gameRaw = envGame ?? fileGame;
  const engineRaw = envEngine ?? fileEngine;
  if (fileMode === "single" && fileGame !== null) {
    fail("invalid-config", "target.yml: mode 'single' with a 'game' field is contradictory");
  }
  if (fileMode === "dual" && fileGame === null && envGame === null) {
    fail("invalid-config", "target.yml: mode 'dual' requires a game root (field 'game' or env MW_TARGET_GAME)");
  }
  let mode;
  if (gameRaw !== null) {
    mode = "dual";
  } else {
    mode = "single";
  }
  if (engineRaw !== null && mode === "single") {
    fail("invalid-config", "target.yml: 'engine' requires dual mode (configure 'game' first)");
  }
  const gameRoot = mode === "dual" ? normalizeRoot(gameRaw, controlRoot) : normalizeRoot(controlRoot, controlRoot);
  return {
    mode,
    controlRoot: normalizeRoot(controlRoot, controlRoot),
    gameRoot,
    engineRoot: engineRaw === null ? null : normalizeRoot(engineRaw, controlRoot),
    parentRoot: null,
    partitionRoot: null,
    roots: null,
    vcs: optionalString(raw.vcs, "vcs"),
    uproject: optionalString(raw.uproject, "uproject"),
    toolchain: parseToolchain(raw.toolchain),
    ignore: parseIgnore(raw.ignore),
    contract: parseContract(raw.contract),
    source: envGame !== null ? "env" : gameRaw !== null || fileMode !== null ? "target-yml" : "default"
  };
}
function resolveWorkspaceConfig(controlRoot) {
  const fileExists = fs2.existsSync(targetYmlPath(controlRoot));
  const raw = rawTargetYml(controlRoot);
  const envGame = process.env[ENV_TARGET_GAME]?.trim() || null;
  const envEngine = process.env[ENV_TARGET_ENGINE]?.trim() || null;
  const envParent = process.env[ENV_PARTITION_PARENT]?.trim() || null;
  const envPartition = process.env[ENV_PARTITION_ROOT]?.trim() || null;
  const fileShape = detectShape(raw, fileExists);
  let active = null;
  if (fileShape === "v2") {
    const value = raw.active;
    active = typeof value === "string" ? value : value === null || value === void 0 ? null : String(value);
  }
  const decision = decideActiveMode({
    fileShape,
    active,
    envPartitionParent: envParent,
    envPartitionRoot: envPartition,
    envTargetGame: envGame,
    envTargetEngine: envEngine
  });
  if (decision.mode === "legacy") {
    return resolveLegacyConfig(controlRoot, raw, envGame, envEngine);
  }
  const controlNorm = normalizeRoot(controlRoot, controlRoot);
  if (decision.mode === "single") {
    checkV2TopWhitelist(raw);
    return {
      mode: "single",
      controlRoot: controlNorm,
      gameRoot: controlNorm,
      engineRoot: null,
      parentRoot: null,
      partitionRoot: null,
      roots: null,
      vcs: null,
      uproject: null,
      toolchain: {},
      ignore: { deny_globs: [] },
      contract: { forbidden_paths: [], conventions: null, docs: [] },
      source: "target-yml"
    };
  }
  if (decision.mode === "dual") {
    const block = v2Block(raw, "dual");
    checkV2TopWhitelist(raw);
    checkBlockKeys(block, "dual", DUAL_BLOCK_KEYS);
    const config = resolveLegacyConfig(
      controlRoot,
      {
        mode: "dual",
        game: block.game,
        engine: block.engine,
        vcs: block.vcs,
        uproject: block.uproject,
        toolchain: block.toolchain,
        ignore: block.ignore,
        contract: block.contract
      },
      envGame,
      envEngine
    );
    return config;
  }
  if (fileShape === "v2") {
    const block = v2Block(raw, "partition");
    checkV2TopWhitelist(raw);
    checkBlockKeys(block, "partition", PARTITION_BLOCK_KEYS);
    return loadPartitionConfig(controlRoot, controlNorm, block, envParent, envPartition, readRootsAst(controlRoot));
  }
  return loadPartitionConfig(controlRoot, controlNorm, null, envParent, envPartition, null);
}
function discoverUproject(gameRoot, explicit) {
  if (explicit !== null && explicit !== void 0) {
    const p = path3.resolve(gameRoot, explicit);
    if (!fs2.existsSync(p)) {
      fail("uproject-not-found", `explicit uproject '${explicit}' not found under game root ${gameRoot}`);
    }
    return p;
  }
  let entries;
  try {
    entries = fs2.readdirSync(gameRoot);
  } catch (err) {
    fail(
      "invalid-config",
      `game root is not readable (${gameRoot}): ${err instanceof Error ? err.message : String(err)}`
    );
  }
  const matches = entries.filter((e) => e.toLowerCase().endsWith(".uproject"));
  if (matches.length !== 1) {
    fail(
      "ambiguous-uproject",
      `expected exactly one *.uproject under game root ${gameRoot}, found ${matches.length}` + (matches.length > 1 ? ` (${matches.join(", ")})` : "")
    );
  }
  return path3.join(gameRoot, matches[0]);
}
function renderToolchainCommand(command, config) {
  if (config.mode === "partition") {
    return renderPartitionCommand(command, config);
  }
  const gameRoot = config.gameRoot;
  if (gameRoot === null) {
    fail("missing-field", `toolchain command requires a game root but none is configured: ${command}`);
  }
  let out = command;
  if (out.includes("{game}")) {
    out = out.split("{game}").join(gameRoot);
  }
  if (out.includes("{engine}")) {
    if (config.engineRoot === null) {
      fail(
        "missing-field",
        `toolchain command references {engine} but engine is not configured (dual mode requires it): ${command}`
      );
    }
    out = out.split("{engine}").join(config.engineRoot);
  }
  if (out.includes("{uproject}")) {
    const uproject = discoverUproject(gameRoot, config.uproject);
    out = out.split("{uproject}").join(uproject);
  }
  return out;
}
var TOKEN_RE = /\{([A-Za-z0-9_-]+)\}/;
function renderPartitionCommand(command, config) {
  let out = command;
  if (config.parentRoot !== null) {
    out = out.split("{parent}").join(config.parentRoot);
  }
  if (config.partitionRoot !== null) {
    out = out.split("{partition}").join(config.partitionRoot);
  }
  const roots = config.roots ?? {};
  for (const [name, root] of Object.entries(roots)) {
    out = out.split(`{${name}}`).join(root);
  }
  const leftover = TOKEN_RE.exec(out);
  if (leftover !== null) {
    const defined = ["{parent}", "{partition}", ...[...Object.keys(roots)].sort().map((n) => `{${n}}`)];
    fail(
      "missing-field",
      `toolchain command references undefined placeholder '${leftover[0]}' (partition mode defines: ${defined.join(
        ", "
      )}): ${command}`
    );
  }
  return out;
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts
var ENV_RAG_SERVERS_FILE = "MW_RAG_SERVERS_FILE";
var ENV_RAG_SERVERS_HOME = "MW_RAG_SERVERS_HOME";
var RAG_SERVERS_BASENAME = "rag-servers.yml";
var DEFAULT_RAG_TIMEOUT_MS = 18e4;
var DEFAULT_RAG_CHAT_BUDGET = 2;
var DEFAULT_RAG_TIME_BUDGET_S = 900;
var RagConfigError = class extends Error {
  constructor(kind, message) {
    super(message);
    this.name = "RagConfigError";
    this.kind = kind;
  }
};
function fail2(kind, message) {
  throw new RagConfigError(kind, message);
}
function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function asObject(value, field) {
  if (!isObject(value)) fail2("invalid-shape", `rag config: field '${field}' must be a mapping`);
  return value;
}
function requireString2(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    fail2("invalid-shape", `rag config: field '${field}' must be a non-empty string`);
  }
  return value;
}
function optionalString2(value, field) {
  return value === void 0 || value === null ? null : requireString2(value, field);
}
function optionalTrimmedString(value, field) {
  const raw = optionalString2(value, field);
  return raw === null ? null : raw.trim();
}
function optionalBoolean(value, field, fallback) {
  if (value === void 0 || value === null) return fallback;
  if (typeof value !== "boolean") fail2("invalid-shape", `rag config: field '${field}' must be a boolean`);
  return value;
}
function optionalNumber(value, field, fallback) {
  if (value === void 0 || value === null) return fallback;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail2("invalid-shape", `rag config: field '${field}' must be a number`);
  }
  return value;
}
function stringArray2(value, field) {
  if (value === void 0 || value === null) return [];
  if (!Array.isArray(value)) fail2("invalid-shape", `rag config: field '${field}' must be a list of strings`);
  return value.map((entry) => requireString2(entry, field));
}
function checkKeys(value, allowed, where) {
  const extra = Object.keys(value).filter((key) => !allowed.has(key));
  if (extra.length > 0) {
    fail2(
      "unknown-key",
      `rag config: unexpected key(s) in ${where}: ${extra.join(", ")} (allowed: ${[...allowed].join(", ")})`
    );
  }
}
function machineRagServersPath(env = process.env) {
  const explicitFile = env[ENV_RAG_SERVERS_FILE]?.trim();
  if (explicitFile !== void 0 && explicitFile !== "") return explicitFile;
  const home = env[ENV_RAG_SERVERS_HOME]?.trim() || env.HOME?.trim() || env.USERPROFILE?.trim();
  if (home === void 0 || home === "") return "";
  return path4.join(home, ".agents", RAG_SERVERS_BASENAME);
}
var RAG_SERVERS_TOP_KEYS = /* @__PURE__ */ new Set(["servers"]);
var RAG_SECTION_KEYS = /* @__PURE__ */ new Set(["enabled", "default_server", "roles", "phases", "budgets"]);
var SERVER_FIELDS = ["transport", "adapter", "path_roots_file", "sources", "capabilities", "mcp", "skill"];
var SERVER_KEYS = new Set(SERVER_FIELDS);
var MCP_KEYS = /* @__PURE__ */ new Set(["url", "token_env", "timeout_ms"]);
var SKILL_KEYS = /* @__PURE__ */ new Set(["dir", "cli_entry", "timeout_ms"]);
var CAPABILITY_KEYS = /* @__PURE__ */ new Set(["graph", "chat", "rewrite"]);
var NESTED_FIELDS = {
  mcp: MCP_KEYS,
  skill: SKILL_KEYS,
  capabilities: CAPABILITY_KEYS
};
var ROLE_KEYS = /* @__PURE__ */ new Set(["server", "source", "require", "rewrite", "chat_budget", "time_budget_s"]);
var PHASE_KEYS = /* @__PURE__ */ new Set(["server", "source", "require", "rewrite"]);
var BUDGET_KEYS = /* @__PURE__ */ new Set(["chat_budget", "time_budget_s"]);
function parseTransport(value, field) {
  if (value === "mcp" || value === "skill" || value === "both") return value;
  fail2("invalid-shape", `rag config: field '${field}' must be one of 'mcp', 'skill', 'both'`);
}
function nestedBlockValue(value, field, name) {
  if (value === void 0 || value === null) return null;
  return asObject(value, `server '${name}'.${field}`);
}
function parseMcp(raw, name) {
  if (raw === null) return null;
  const url = optionalTrimmedString(raw.url, `server '${name}'.mcp.url`);
  if (url === null) fail2("mcp-missing-url", `rag server '${name}': mcp.url is required`);
  return {
    url,
    tokenEnv: optionalTrimmedString(raw.token_env, `server '${name}'.mcp.token_env`),
    timeoutMs: optionalNumber(raw.timeout_ms, `server '${name}'.mcp.timeout_ms`, DEFAULT_RAG_TIMEOUT_MS)
  };
}
function parseSkill(raw, name) {
  if (raw === null) return null;
  const dir = optionalTrimmedString(raw.dir, `server '${name}'.skill.dir`);
  const cliEntry = optionalTrimmedString(raw.cli_entry, `server '${name}'.skill.cli_entry`);
  if (cliEntry === null) fail2("skill-missing-cli", `rag server '${name}': skill.cli_entry is required`);
  return {
    dir,
    cliEntry,
    timeoutMs: optionalNumber(raw.timeout_ms, `server '${name}'.skill.timeout_ms`, DEFAULT_RAG_TIMEOUT_MS)
  };
}
function parseCapabilities(raw, name) {
  if (raw === null) return { graph: false, chat: false, rewrite: false };
  return {
    graph: optionalBoolean(raw.graph, `server '${name}'.capabilities.graph`, false),
    chat: optionalBoolean(raw.chat, `server '${name}'.capabilities.chat`, false),
    rewrite: optionalBoolean(raw.rewrite, `server '${name}'.capabilities.rewrite`, false)
  };
}
function mergeServerEntry(machine, project, name) {
  const machineObj = machine === void 0 || machine === null ? null : asObject(machine, `server '${name}' (machine)`);
  const projectObj = project === void 0 || project === null ? null : asObject(project, `server '${name}' (project)`);
  if (machineObj !== null) checkKeys(machineObj, SERVER_KEYS, `server '${name}' (machine)`);
  if (projectObj !== null) checkKeys(projectObj, SERVER_KEYS, `server '${name}' (project)`);
  const machineRecord = machineObj ?? {};
  const projectRecord = projectObj ?? {};
  const origin = {};
  const merged = {};
  for (const field of SERVER_FIELDS) {
    const inMachine = field in machineRecord;
    const inProject = field in projectRecord;
    if (!inMachine && !inProject) continue;
    const machineValue = inMachine ? machineRecord[field] : void 0;
    const projectValue = inProject ? projectRecord[field] : void 0;
    if (inProject && projectValue === null) {
      merged[field] = null;
      origin[field] = "project";
      continue;
    }
    if (inMachine && machineValue === null && !inProject) continue;
    const nestedFields = NESTED_FIELDS[field];
    if (nestedFields !== void 0) {
      const nested = {};
      if (inMachine && machineValue !== void 0 && machineValue !== null) {
        const machineBlock = asObject(machineValue, `server '${name}'.${field} (machine)`);
        checkKeys(machineBlock, nestedFields, `server '${name}'.${field} (machine)`);
        for (const key of Object.keys(machineBlock)) {
          nested[key] = machineBlock[key];
          origin[`${field}.${key}`] = "machine";
        }
      }
      if (inProject && projectValue !== void 0 && projectValue !== null) {
        const projectBlock = asObject(projectValue, `server '${name}'.${field} (project)`);
        checkKeys(projectBlock, nestedFields, `server '${name}'.${field} (project)`);
        for (const key of Object.keys(projectBlock)) {
          if (projectBlock[key] === null) delete nested[key];
          else nested[key] = projectBlock[key];
          origin[`${field}.${key}`] = "project";
        }
      }
      merged[field] = Object.keys(nested).length > 0 ? nested : null;
      continue;
    }
    if (inProject) {
      merged[field] = projectValue;
      origin[field] = "project";
    } else {
      merged[field] = machineValue;
      origin[field] = "machine";
    }
  }
  const rawTransport = merged.transport;
  const transport2 = rawTransport === void 0 || rawTransport === null ? "mcp" : parseTransport(rawTransport, `server '${name}'.transport`);
  let adapter = "overcode-v1";
  if (merged.adapter !== void 0 && merged.adapter !== null) {
    adapter = requireString2(merged.adapter, `server '${name}'.adapter`);
  }
  if (adapter !== "overcode-v1") {
    fail2("invalid-shape", `rag server '${name}': unsupported adapter '${adapter}' (only 'overcode-v1')`);
  }
  const pathRootsFile = optionalString2(merged.path_roots_file, `server '${name}'.path_roots_file`);
  const sources = stringArray2(merged.sources, `server '${name}'.sources`);
  const mcp = parseMcp(nestedBlockValue(merged.mcp, "mcp", name), name);
  const skill = parseSkill(nestedBlockValue(merged.skill, "skill", name), name);
  const capabilities = parseCapabilities(nestedBlockValue(merged.capabilities, "capabilities", name), name);
  if ((transport2 === "mcp" || transport2 === "both") && mcp === null) {
    fail2("mcp-missing-url", `rag server '${name}': transport '${transport2}' requires an 'mcp' block with a url`);
  }
  if ((transport2 === "skill" || transport2 === "both") && skill === null) {
    fail2(
      "skill-missing-cli",
      `rag server '${name}': transport '${transport2}' requires a 'skill' block with a cli_entry`
    );
  }
  return {
    transport: transport2,
    mcp,
    skill,
    adapter: "overcode-v1",
    pathRootsFile,
    pathRootsDigest: null,
    sources,
    capabilities,
    origin
  };
}
function readYamlMapping(file, label) {
  let text;
  try {
    text = fs3.readFileSync(file, "utf-8");
  } catch {
    return {};
  }
  if (text.replace(/^\uFEFF/, "").trim() === "") return {};
  let parsed;
  try {
    parsed = (0, import_yaml2.parse)(text);
  } catch (err) {
    fail2("bad-yaml", `${label} is not valid YAML (${file}): ${err instanceof Error ? err.message : String(err)}`);
  }
  if (parsed === void 0 || parsed === null) {
    fail2("invalid-shape", `${label}: top level must be a mapping (${file})`);
  }
  if (!isObject(parsed)) fail2("invalid-shape", `${label}: top level must be a mapping (${file})`);
  return parsed;
}
function readServersTable(file, label) {
  if (file === "") return {};
  const raw = readYamlMapping(file, label);
  checkKeys(raw, RAG_SERVERS_TOP_KEYS, `${label} top level`);
  const servers = raw.servers;
  if (servers === void 0 || servers === null) return {};
  return asObject(servers, `${label} 'servers'`);
}
function readRagSection(controlRoot) {
  const rag = rawTargetYml(controlRoot).rag;
  if (rag === void 0 || rag === null) return {};
  const section = asObject(rag, "target.yml 'rag'");
  checkKeys(section, RAG_SECTION_KEYS, "target.yml 'rag' section");
  return section;
}
function parseEnabled(value) {
  if (value === void 0 || value === null) return [];
  if (!Array.isArray(value)) fail2("invalid-shape", "target.yml rag.enabled must be a list of server names");
  return value.map((entry) => {
    if (typeof entry !== "string") fail2("invalid-shape", "target.yml rag.enabled must be a list of server names");
    if (entry.trim() === "") fail2("enabled-empty-entry", "target.yml rag.enabled must not contain empty entries");
    return entry;
  });
}
function parseBudgets(value) {
  if (value === void 0 || value === null) {
    return { chat: DEFAULT_RAG_CHAT_BUDGET, timeS: DEFAULT_RAG_TIME_BUDGET_S };
  }
  const raw = asObject(value, "target.yml rag.budgets");
  checkKeys(raw, BUDGET_KEYS, "target.yml rag.budgets");
  return {
    chat: optionalNumber(raw.chat_budget, "target.yml rag.budgets.chat_budget", DEFAULT_RAG_CHAT_BUDGET),
    timeS: optionalNumber(raw.time_budget_s, "target.yml rag.budgets.time_budget_s", DEFAULT_RAG_TIME_BUDGET_S)
  };
}
function parseRoleSpecs(value) {
  if (value === void 0 || value === null) return {};
  const raw = asObject(value, "target.yml rag.roles");
  const out = {};
  for (const [role, entry] of Object.entries(raw)) {
    if (entry === void 0 || entry === null) continue;
    const spec = asObject(entry, `target.yml rag.roles.${role}`);
    checkKeys(spec, ROLE_KEYS, `target.yml rag.roles.${role}`);
    const parsed = {};
    if (spec.server !== void 0 && spec.server !== null) {
      parsed.server = requireString2(spec.server, `rag.roles.${role}.server`);
    }
    if (spec.source !== void 0 && spec.source !== null) {
      parsed.source = requireString2(spec.source, `rag.roles.${role}.source`);
    }
    if (spec.require !== void 0 && spec.require !== null) {
      parsed.require = optionalBoolean(spec.require, `rag.roles.${role}.require`, false);
    }
    if (spec.rewrite !== void 0 && spec.rewrite !== null) {
      parsed.rewrite = optionalBoolean(spec.rewrite, `rag.roles.${role}.rewrite`, false);
    }
    if (spec.chat_budget !== void 0 && spec.chat_budget !== null) {
      parsed.chatBudget = optionalNumber(spec.chat_budget, `rag.roles.${role}.chat_budget`, 0);
    }
    if (spec.time_budget_s !== void 0 && spec.time_budget_s !== null) {
      parsed.timeBudgetS = optionalNumber(spec.time_budget_s, `rag.roles.${role}.time_budget_s`, 0);
    }
    out[role] = parsed;
  }
  return out;
}
function parsePhaseSpecs(value) {
  if (value === void 0 || value === null) return {};
  const raw = asObject(value, "target.yml rag.phases");
  const out = {};
  for (const [phase, entry] of Object.entries(raw)) {
    if (entry === void 0 || entry === null) continue;
    const spec = asObject(entry, `target.yml rag.phases.${phase}`);
    checkKeys(spec, PHASE_KEYS, `target.yml rag.phases.${phase}`);
    const parsed = {};
    if (spec.server !== void 0 && spec.server !== null) {
      parsed.server = requireString2(spec.server, `rag.phases.${phase}.server`);
    }
    if (spec.source !== void 0 && spec.source !== null) {
      parsed.source = requireString2(spec.source, `rag.phases.${phase}.source`);
    }
    if (spec.require !== void 0 && spec.require !== null) {
      parsed.require = optionalBoolean(spec.require, `rag.phases.${phase}.require`, false);
    }
    if (spec.rewrite !== void 0 && spec.rewrite !== null) {
      parsed.rewrite = optionalBoolean(spec.rewrite, `rag.phases.${phase}.rewrite`, false);
    }
    out[phase] = parsed;
  }
  return out;
}
function unknownServer(name, visible) {
  fail2(
    "unknown-server",
    `unknown rag server '${name}' (visible: ${visible.length > 0 ? visible.join(", ") : "none"})`
  );
}
function loadRagConfig(controlRoot) {
  const machineTable = readServersTable(machineRagServersPath(), "machine rag-servers.yml");
  const projectFile = path4.join(controlRoot, ".mw", RAG_SERVERS_BASENAME);
  const projectTable = readServersTable(projectFile, "project rag-servers.yml");
  const rag = readRagSection(controlRoot);
  const names = [.../* @__PURE__ */ new Set([...Object.keys(machineTable), ...Object.keys(projectTable)])].sort();
  const servers = {};
  for (const name of names) {
    const entry = mergeServerEntry(machineTable[name], projectTable[name], name);
    entry.pathRootsDigest = pathRootsDigest(controlRoot, entry.pathRootsFile);
    servers[name] = entry;
  }
  const visible = Object.keys(servers);
  const enabled = parseEnabled(rag.enabled);
  for (const name of enabled) {
    if (!(name in servers)) unknownServer(name, visible);
  }
  const defaultServer = optionalString2(rag.default_server, "target.yml rag.default_server");
  if (defaultServer !== null && !(defaultServer in servers)) unknownServer(defaultServer, visible);
  const roles = parseRoleSpecs(rag.roles);
  for (const spec of Object.values(roles)) {
    if (spec.server !== void 0 && !(spec.server in servers)) unknownServer(spec.server, visible);
  }
  const phases = parsePhaseSpecs(rag.phases);
  for (const spec of Object.values(phases)) {
    if (spec.server !== void 0 && !(spec.server in servers)) unknownServer(spec.server, visible);
  }
  const budgets = parseBudgets(rag.budgets);
  const config = { enabled, defaultServer, servers, roles, phases, budgets, fingerprint: "" };
  config.fingerprint = ragFingerprint(config);
  return config;
}
var RESEARCH_ROLES = /* @__PURE__ */ new Set(["spec", "design", "research", "rag-research"]);
var RESEARCH_PHASES = /* @__PURE__ */ new Set(["spec", "design"]);
function rewriteDefaults(role, phase, capabilityRewrite, explicit) {
  if (explicit !== void 0) return explicit;
  const researchLike = RESEARCH_ROLES.has(role) || RESEARCH_PHASES.has(phase);
  return researchLike && capabilityRewrite;
}
function resolveDefaults(config, role, phase) {
  const roleSpec = role !== "" ? config.roles[role] : void 0;
  const phaseSpec = phase !== "" ? config.phases[phase] : void 0;
  const server = roleSpec?.server ?? phaseSpec?.server ?? config.defaultServer ?? null;
  const source = roleSpec?.source ?? phaseSpec?.source ?? null;
  const explicit = roleSpec?.rewrite ?? phaseSpec?.rewrite;
  const capabilityRewrite = server !== null && config.servers[server]?.capabilities.rewrite === true;
  return { server, source, rewrite: rewriteDefaults(role, phase, capabilityRewrite, explicit) };
}
function requiredFor(config, role, phase) {
  return config.roles[role]?.require === true || config.phases[phase]?.require === true;
}
function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (isObject(value)) {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key]);
    return out;
  }
  return value;
}
function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}
function pathRootsDigest(controlRoot, file) {
  if (file === null) return null;
  const target = path4.isAbsolute(file) ? file : path4.join(controlRoot, file);
  try {
    return createHash("sha256").update(fs3.readFileSync(target)).digest("hex");
  } catch {
    return null;
  }
}
function roleSpecToSnake(spec) {
  const out = {};
  if (spec.server !== void 0) out.server = spec.server;
  if (spec.source !== void 0) out.source = spec.source;
  if (spec.require !== void 0) out.require = spec.require;
  if (spec.rewrite !== void 0) out.rewrite = spec.rewrite;
  if (spec.chatBudget !== void 0) out.chat_budget = spec.chatBudget;
  if (spec.timeBudgetS !== void 0) out.time_budget_s = spec.timeBudgetS;
  return out;
}
function phaseSpecToSnake(spec) {
  const out = {};
  if (spec.server !== void 0) out.server = spec.server;
  if (spec.source !== void 0) out.source = spec.source;
  if (spec.require !== void 0) out.require = spec.require;
  if (spec.rewrite !== void 0) out.rewrite = spec.rewrite;
  return out;
}
function ragFingerprint(config, enabledOnly) {
  const names = [...new Set(enabledOnly ?? config.enabled)].sort();
  const servers = names.map((name) => {
    const entry = config.servers[name];
    if (entry === void 0) unknownServer(name, Object.keys(config.servers));
    return {
      name,
      transport: entry.transport,
      adapter: entry.adapter,
      mcp: entry.mcp === null ? null : { url: entry.mcp.url, token_env: entry.mcp.tokenEnv, timeout_ms: entry.mcp.timeoutMs },
      skill: entry.skill === null ? null : { dir: entry.skill.dir, cli_entry: entry.skill.cliEntry, timeout_ms: entry.skill.timeoutMs },
      path_roots_file: entry.pathRootsFile,
      path_roots_digest: entry.pathRootsDigest,
      sources: entry.sources,
      capabilities: entry.capabilities
    };
  });
  const roles = {};
  for (const role of Object.keys(config.roles)) roles[role] = roleSpecToSnake(config.roles[role]);
  const phases = {};
  for (const phase of Object.keys(config.phases)) phases[phase] = phaseSpecToSnake(config.phases[phase]);
  const payload = {
    enabled: names,
    servers,
    default_server: config.defaultServer,
    roles,
    phases,
    budgets: { chat_budget: config.budgets.chat, time_budget_s: config.budgets.timeS }
  };
  return createHash("sha256").update(canonicalJson(payload)).digest("hex");
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/evidence.ts
import * as path6 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts
import * as fs4 from "node:fs";
import * as path5 from "node:path";
function outputDir(taskKey, agenticdocRoot2) {
  const resolved = path5.resolve(agenticdocRoot2, taskKey);
  const root = path5.resolve(agenticdocRoot2);
  if (!resolved.startsWith(`${root}${path5.sep}`) && resolved !== root) {
    throw new Error(`Invalid taskKey: path traversal detected in "${taskKey}"`);
  }
  return resolved;
}
var HEADLINE_MARKER_RE = /^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/;
function headline(summary) {
  const firstLine2 = summary.split("\n").find((line) => line.trim() !== "") ?? "";
  let s = firstLine2.trim();
  while (HEADLINE_MARKER_RE.test(s)) {
    s = s.replace(HEADLINE_MARKER_RE, "").trim();
  }
  s = s.replace(/\s+/g, " ");
  return s === "" ? "(no conclusion)" : truncLine(s, 100);
}
function writeOutput(opts) {
  const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
  fs4.mkdirSync(dir, { recursive: true });
  const outputPath = path5.join(dir, "output.md");
  const sections = [];
  sections.push(`## TL;DR

${headline(opts.summary)}`);
  sections.push(`## Summary

${opts.summary || "(no summary)"}`);
  if (opts.exitCode === 0) {
    const files = opts.changedFiles?.join("\n") ?? "(none)";
    sections.push(`## Changed Files

${files}`);
    sections.push(`## Verification Steps

${opts.verificationSteps || "(none)"}`);
    sections.push(`## Exit Reason

${opts.exitReason || "Task completed successfully."}`);
  } else if (opts.exitCode === 1) {
    sections.push(`## Exit Reason

${opts.exitReason || "Task failed."}`);
  } else if (opts.exitCode === 2) {
    sections.push(`## Questions

${opts.questions || "(no questions provided)"}`);
  } else if (opts.exitCode === 130) {
    sections.push(`## Exit Reason

Task was cancelled (exit 130).`);
  }
  let existing = "";
  try {
    existing = fs4.readFileSync(outputPath, "utf8");
  } catch {
    existing = "";
  }
  const body = `${sections.join("\n\n")}
`;
  fs4.writeFileSync(outputPath, existing.trim() === "" ? body : `${existing.trimEnd()}

---

${body}`, "utf8");
}
function appendTrace(taskKey, agenticdocRoot2, line) {
  const dir = outputDir(taskKey, agenticdocRoot2);
  fs4.mkdirSync(dir, { recursive: true });
  const tracePath = path5.join(dir, "trace.log");
  const ts = (/* @__PURE__ */ new Date()).toISOString();
  fs4.appendFileSync(tracePath, `[FLOW] ${ts} ${line}
`, "utf8");
}
function appendLifecycleLine(taskKey, agenticdocRoot2, line) {
  const dir = outputDir(taskKey, agenticdocRoot2);
  fs4.mkdirSync(dir, { recursive: true });
  fs4.appendFileSync(path5.join(dir, "trace.log"), `${line}
`, "utf8");
}
function truncLine(s, max) {
  return s.length <= max ? s : `${s.slice(0, max - 1)}\u2026`;
}
function appendStart(taskKey, agenticdocRoot2, type, phaseTotal) {
  appendLifecycleLine(
    taskKey,
    agenticdocRoot2,
    `[START] ${(/* @__PURE__ */ new Date()).toISOString()} task=${taskKey} type=${type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`
  );
}
function appendModel(taskKey, agenticdocRoot2, modelId) {
  appendLifecycleLine(taskKey, agenticdocRoot2, `[MODEL] ${(/* @__PURE__ */ new Date()).toISOString()} model=${modelId}`);
}
function appendPhase(taskKey, agenticdocRoot2, state, idx, total, name = "") {
  const tail = state === "start" && name ? ` ${truncLine(name, 60)}` : "";
  appendLifecycleLine(taskKey, agenticdocRoot2, `[PHASE] ${(/* @__PURE__ */ new Date()).toISOString()} ${state} ${idx}/${total}${tail}`);
}
function appendTool(taskKey, agenticdocRoot2, toolName, target) {
  appendLifecycleLine(
    taskKey,
    agenticdocRoot2,
    `[TOOL] ${(/* @__PURE__ */ new Date()).toISOString()} ${toolName}${target ? ` ${truncLine(target, 80)}` : ""}`
  );
}
function appendToolError(taskKey, agenticdocRoot2, toolName, message) {
  appendLifecycleLine(
    taskKey,
    agenticdocRoot2,
    `[TOOL_ERR] ${(/* @__PURE__ */ new Date()).toISOString()} ${toolName} ${truncLine(message, 120)}`
  );
}
function appendTimeout(taskKey, agenticdocRoot2, kind, detail) {
  appendLifecycleLine(taskKey, agenticdocRoot2, `[TIMEOUT] ${(/* @__PURE__ */ new Date()).toISOString()} ${kind}: ${detail}`);
}
function appendCheckpoint(taskKey, agenticdocRoot2, opts) {
  appendLifecycleLine(
    taskKey,
    agenticdocRoot2,
    `[CHECKPOINT] ${(/* @__PURE__ */ new Date()).toISOString()} elapsed=${Math.round(opts.elapsedMs / 1e3)}s reads=${opts.reads} writes=${opts.writes} phases=${opts.phases} uniq_targets=${opts.uniqTargets} repeat_top=${opts.repeatTop} risk=${opts.risk}`
  );
}
function appendError(taskKey, agenticdocRoot2, message) {
  appendLifecycleLine(
    taskKey,
    agenticdocRoot2,
    `[ERROR] ${(/* @__PURE__ */ new Date()).toISOString()} ${truncLine(message.split("\n")[0] ?? "", 160)}`
  );
}
function appendEnd(taskKey, agenticdocRoot2, opts) {
  const phases = opts.phaseTotal && opts.phaseTotal > 0 ? `${opts.phaseDone ?? 0}/${opts.phaseTotal}` : "-";
  appendLifecycleLine(
    taskKey,
    agenticdocRoot2,
    `[END] ${(/* @__PURE__ */ new Date()).toISOString()} exit=${opts.exitCode} elapsed=${Math.round(
      opts.elapsedMs / 1e3
    )}s tools=${opts.toolCalls} phases=${phases}`
  );
}
function appendGoalCheck(taskKey, agenticdocRoot2, phaseNum, goalMtimeMs) {
  const dir = outputDir(taskKey, agenticdocRoot2);
  fs4.mkdirSync(dir, { recursive: true });
  const tracePath = path5.join(dir, "trace.log");
  fs4.appendFileSync(tracePath, `[GOAL_CHECK] phase=${phaseNum} goal_mtime=${goalMtimeMs}
`, "utf8");
}
function appendHeartbeat(taskKey, agenticdocRoot2, phase) {
  const dir = outputDir(taskKey, agenticdocRoot2);
  fs4.mkdirSync(dir, { recursive: true });
  const tracePath = path5.join(dir, "trace.log");
  const ts = (/* @__PURE__ */ new Date()).toISOString();
  fs4.appendFileSync(tracePath, `[HEARTBEAT] ${ts} task=${taskKey} phase=${phase}
`, "utf8");
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/evidence.ts
var RAG_FALLBACK = "rag_fallback";
var RAG_UNAVAILABLE = "rag-unavailable";
var RAG_REWRITE_DEGRADED = "rag-rewrite-degraded";
var RAG_REQUIRED_MISSING = "rag-required-missing";
var RAG_BUDGET_EXCEEDED = "rag-budget-exceeded";
function count(value) {
  return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
}
function ragCallLine(e) {
  const line = `rag_call server=${e.server} tool=${e.tool} via=${e.via} ms=${count(e.ms)} results=${count(e.results)}`;
  return e.mcpTool !== void 0 && e.mcpTool !== null && e.mcpTool.length > 0 ? `${line} mcp_tool=${e.mcpTool}` : line;
}
function ragFallbackLine(e) {
  return `${RAG_FALLBACK} server=${e.server} tool=${e.tool} via=cli reason=${e.reason}`;
}
function ragUnavailableLine(e) {
  return `${RAG_UNAVAILABLE} server=${e.server} tool=${e.tool} kind=${e.kind} ms=${count(e.ms)}`;
}
function ragBudgetExceededLine(e) {
  return `${RAG_BUDGET_EXCEEDED} server=${e.server} tool=${e.tool} reason=${e.reason} used=${count(
    e.used
  )} budget=${count(e.budget)}`;
}
function ragRewriteDegradedLine(e) {
  return `${RAG_REWRITE_DEGRADED} server=${e.server} tool=${e.tool}`;
}
function ragRequiredMissingLine(e) {
  return `${RAG_REQUIRED_MISSING} role=${e.role} phase=${e.phase} server=${e.server}`;
}
function appendEvidence(taskDir, line) {
  const resolved = path6.resolve(taskDir);
  appendTrace(path6.basename(resolved), path6.dirname(resolved), line);
}
function redactSecrets(text, tokenEnvNames) {
  let redacted = text;
  for (const envName of tokenEnvNames) {
    const value = process.env[envName];
    if (value === void 0 || value.length === 0) continue;
    if (!redacted.includes(value)) continue;
    redacted = redacted.split(value).join("<redacted>");
  }
  return redacted;
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/research-doc.ts
import * as fs6 from "node:fs";
import * as path8 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/rag/adapter.ts
import * as fs5 from "node:fs";
import * as path7 from "node:path";
var DEFAULT_ROLE = "engine";
var GRAPH_TOOLS = /* @__PURE__ */ new Set(["rag_graph", "rag_impact"]);
var CHAT_TOOLS = /* @__PURE__ */ new Set(["rag_chat"]);
var META_KEYS = /* @__PURE__ */ new Set([
  "affected_files",
  "answer",
  "callers_by_hop",
  "count",
  "depth",
  "file",
  "lead_only",
  "multiple_matches",
  "note",
  "operation",
  "resolved_symbol",
  "rewrite_degraded",
  "static_analysis",
  "status",
  "symbol"
]);
var ITEM_ARRAY_KEYS = ["documents", "results", "symbols", "items"];
function fail3(message) {
  throw new RagConfigError("invalid-shape", message);
}
function optionalString3(value) {
  return typeof value === "string" && value.length > 0 ? value : null;
}
function optionalNumber2(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function formatCitation(c) {
  if (c.server.length === 0 || c.server.includes(":")) {
    fail3(`citation server must be non-empty and contain no ':' (got ${JSON.stringify(c.server)})`);
  }
  if (c.source.length === 0 || c.source.includes(":")) {
    fail3(`citation source must be non-empty and contain no ':' (got ${JSON.stringify(c.source)})`);
  }
  if (!Number.isInteger(c.line) || c.line < 0) {
    fail3(`citation line must be a non-negative integer (got ${String(c.line)})`);
  }
  return `${c.server}:${c.source}:${c.filePath}:${c.line}`;
}
function parseCitation(text) {
  if (typeof text !== "string") return null;
  const firstColon = text.indexOf(":");
  if (firstColon <= 0) return null;
  const server = text.slice(0, firstColon);
  const afterServer = text.slice(firstColon + 1);
  const secondColon = afterServer.indexOf(":");
  if (secondColon <= 0) return null;
  const source = afterServer.slice(0, secondColon);
  const tail = afterServer.slice(secondColon + 1);
  const lastColon = tail.lastIndexOf(":");
  if (lastColon < 0) return null;
  const filePath = tail.slice(0, lastColon);
  const lineText = tail.slice(lastColon + 1);
  if (filePath.length === 0 || !/^\d+$/.test(lineText)) return null;
  const line = Number.parseInt(lineText, 10);
  if (!Number.isSafeInteger(line)) return null;
  return { server, source, filePath, line };
}
function loadPathRoots(pathRootsFile) {
  if (pathRootsFile === null || pathRootsFile.length === 0) return null;
  let text;
  try {
    text = fs5.readFileSync(pathRootsFile, "utf8");
  } catch (error) {
    const code = error.code;
    if (code === "ENOENT" || code === "ENOTDIR") return null;
    fail3(`cannot read path_roots file ${pathRootsFile}: ${String(error)}`);
  }
  const withoutBom = text.startsWith("\uFEFF") ? text.slice(1) : text;
  let parsed;
  try {
    parsed = JSON.parse(withoutBom);
  } catch (error) {
    fail3(`path_roots file is not valid JSON: ${pathRootsFile}: ${String(error)}`);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    fail3(`path_roots file must contain a JSON object: ${pathRootsFile}`);
  }
  const roots = {};
  for (const [key, value] of Object.entries(parsed)) {
    if (key.startsWith("_")) continue;
    if (typeof value !== "string" || value.trim().length === 0) {
      fail3(`path_roots entry '${key}' must be a non-empty path string`);
    }
    roots[key] = value;
  }
  return roots;
}
function resolveLocalPath(filePath, roots) {
  if (roots === null) {
    return { localPath: null, exists: false, lineHint: null, reason: "path_roots not configured" };
  }
  let role = DEFAULT_ROLE;
  let relative8 = filePath;
  const separator = filePath.indexOf("::");
  if (separator >= 0) {
    role = filePath.slice(0, separator).trim();
    relative8 = filePath.slice(separator + 2);
  }
  if (!Object.hasOwn(roots, role)) {
    const available = Object.keys(roots).sort().join(", ");
    return {
      localPath: null,
      exists: false,
      lineHint: null,
      reason: `unknown role '${role}' (available roles: ${available})`
    };
  }
  const normalizedRelative = relative8.trim().replace(/\\/g, "/").replace(/^\/+/, "");
  const root = path7.resolve(roots[role]);
  const resolved = path7.resolve(root, normalizedRelative);
  if (!isInside(root, resolved)) {
    return {
      localPath: null,
      exists: false,
      lineHint: null,
      reason: `path traversal escapes role '${role}' root: ${filePath}`
    };
  }
  let exists = false;
  try {
    exists = fs5.statSync(resolved).isFile();
  } catch {
    exists = false;
  }
  return { localPath: resolved, exists, lineHint: null, reason: exists ? null : "file missing" };
}
function isInside(root, candidate) {
  const relative8 = path7.relative(root, candidate);
  if (relative8 === "") return true;
  if (path7.isAbsolute(relative8)) return false;
  return relative8.split(/[\\/]/)[0] !== "..";
}
var RAG_TOOL_MAP = {
  rag_search: { mcp: ["rag_search"], multi: "rag_search_multi_rounds" },
  rag_symbol: { mcp: ["rag_symbol"] },
  rag_graph: { mcp: ["graph_query"] },
  rag_impact: { mcp: ["rag_impact"] },
  rag_sources: { mcp: ["list_sources", "list_collections"], merge: "sources" },
  rag_feedback: { mcp: ["rag_feedback"] },
  rag_chat: { mcp: ["rag_chat"] }
};
var REWRITE_SWITCHES = /* @__PURE__ */ new Set(["multi_rounds", "auto_rewrite"]);
var RAG_TOOL_TABLE = RAG_TOOL_MAP;
function toolTarget(logical) {
  if (!Object.hasOwn(RAG_TOOL_MAP, logical)) {
    fail3(`unknown logical rag tool '${logical}' (no RAG_TOOL_MAP entry)`);
  }
  const target = RAG_TOOL_TABLE[logical];
  if (target === void 0 || target.mcp.length === 0) {
    fail3(`RAG_TOOL_MAP entry for '${logical}' has no server tool`);
  }
  return target;
}
function ragToolCalls(logical, args) {
  const target = toolTarget(logical);
  if (target.multi !== void 0 && (args.multi_rounds === true || args.auto_rewrite === true)) {
    return [{ name: target.multi, args: withoutRewriteSwitches(args) }];
  }
  return target.mcp.map((name) => ({ name, args: { ...args } }));
}
function withoutRewriteSwitches(args) {
  const next = {};
  for (const [key, value] of Object.entries(args)) {
    if (REWRITE_SWITCHES.has(key)) continue;
    next[key] = value;
  }
  return next;
}
function mergeToolResponses(logical, responses) {
  const target = toolTarget(logical);
  if (target.merge === "sources") {
    if (responses.length !== target.mcp.length) {
      fail3(`rag_sources expects ${target.mcp.length} responses, got ${responses.length}`);
    }
    return mergeSourcesResponses(responses[0], responses[1]);
  }
  if (responses.length !== 1) {
    fail3(`${logical} expects a single response, got ${responses.length}`);
  }
  return responses[0];
}
function mergeSourcesResponses(sourcesRaw, collectionsRaw) {
  const sources = listedEntries(sourcesRaw, "sources", "list_sources");
  const collections = listedEntries(collectionsRaw, "collections", "list_collections");
  const results = [];
  for (const entry of sources) results.push(listingItem(entry, "source", "list_sources"));
  for (const entry of collections) results.push(listingItem(entry, "collection", "list_collections"));
  return { results, sources, collections };
}
function listedEntries(raw, key, tool) {
  const record = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? raw : null;
  const value = record === null ? void 0 : record[key];
  if (!Array.isArray(value)) fail3(`${tool} response is missing the '${key}' array`);
  const entries = [];
  for (const entry of value) {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      fail3(`${tool} ${key} entry is not an object`);
    }
    entries.push(entry);
  }
  return entries;
}
function listingItem(entry, kind, tool) {
  const name = optionalString3(entry.name);
  if (name === null) fail3(`${tool} entry is missing a 'name'`);
  return {
    ...entry,
    file_path: optionalString3(entry.file_path) ?? name,
    symbol_name: optionalString3(entry.symbol_name) ?? name,
    symbol_type: kind,
    snippet: JSON.stringify(entry)
  };
}
function capabilityError(server, tool, caps) {
  if (GRAPH_TOOLS.has(tool) && !caps.graph) {
    return { kind: "capability", server, tool, message: `no knowledge graph for server ${server}` };
  }
  if (CHAT_TOOLS.has(tool) && !caps.chat) {
    return { kind: "capability", server, tool, message: `no chat capability for server ${server}` };
  }
  return null;
}
function normalizeResults(server, tool, source, raw, roots) {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    fail3(`${tool} response must be a JSON object`);
  }
  const record = raw;
  const meta = {};
  for (const key of Object.keys(record)) {
    if (key.startsWith("total_") || META_KEYS.has(key)) meta[key] = record[key];
  }
  if (roots === null) meta.hint = "path_roots not configured; set path_roots_file to resolve local_path";
  const rawItems = locateItems(record, tool);
  const items = rawItems.map((entry, index) => normalizeItem(server, tool, source, entry, roots, index));
  return { server, tool, source, snapshot: true, items, meta };
}
function locateItems(record, tool) {
  if (typeof record.file_path === "string" && record.file_path.length > 0) {
    return [record];
  }
  for (const key of ITEM_ARRAY_KEYS) {
    const value = record[key];
    if (Array.isArray(value)) return value;
  }
  if (Array.isArray(record.affected_files)) return record.affected_files;
  if (Array.isArray(record.candidates)) return record.candidates;
  fail3(`${tool} response has no recognized result array (documents/results/symbols/items/affected_files)`);
}
function normalizeItem(server, tool, source, entry, roots, index) {
  if (typeof entry === "string") {
    const filePath2 = entry.trim();
    if (filePath2.length === 0) fail3(`${tool} result[${index}] is an empty file path`);
    return buildItem(server, source, filePath2, null, null, null, roots);
  }
  if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
    fail3(`${tool} result[${index}] is not an object`);
  }
  const item = entry;
  const filePath = optionalString3(item.file_path) ?? optionalString3(item.file) ?? optionalString3(item.path);
  if (filePath === null) {
    fail3(`${tool} result[${index}] is missing file_path`);
  }
  return buildItem(
    server,
    source,
    filePath,
    optionalNumber2(item.line_start),
    optionalString3(item.symbol_name) ?? optionalString3(item.name),
    optionalString3(item.qualified_name),
    roots,
    {
      symbolType: optionalString3(item.symbol_type) ?? optionalString3(item.kind),
      snippet: optionalString3(item.content) ?? optionalString3(item.snippet),
      score: optionalNumber2(item.score),
      lineEnd: optionalNumber2(item.line_end)
    }
  );
}
function buildItem(server, source, filePath, lineStart, symbolName, qualifiedName, roots, extras) {
  const resolved = resolveLocalPath(filePath, roots);
  const citation = source === null || lineStart === null ? null : formatCitation({ server, source, filePath, line: lineStart });
  return {
    symbol_name: symbolName ?? "",
    qualified_name: qualifiedName,
    symbol_type: extras?.symbolType ?? null,
    file_path: filePath,
    line_start: lineStart,
    line_end: extras?.lineEnd ?? null,
    snippet: extras?.snippet ?? null,
    score: extras?.score ?? null,
    citation,
    local_path: resolved.localPath,
    exists: resolved.exists,
    line_hint: lineStart,
    snapshot_warning: true
  };
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/research-doc.ts
var RESEARCH_DOC_SECTIONS = ["\u67E5\u8BE2", "\u7ED3\u8BBA", "\u5F15\u7528", "\u672A\u89E3\u51B3", "\u5FEB\u7167", "\u5F71\u54CD\u9762"];
var RESEARCH_DOC_HEADINGS = RESEARCH_DOC_SECTIONS.map((section) => `## ${section}`);
function researchDocDir(keyDir) {
  return path8.join(keyDir, "rag");
}
function listResearchDocs(keyDir) {
  let names;
  try {
    names = fs6.readdirSync(researchDocDir(keyDir));
  } catch {
    return [];
  }
  return names.filter((name) => name.endsWith(".md") && !name.startsWith(".")).map((name) => path8.join(researchDocDir(keyDir), name)).sort();
}
function splitResearchDocSections(text) {
  const sections = /* @__PURE__ */ new Map();
  let current = null;
  for (const raw of text.split(/\r?\n/)) {
    const match2 = /^##\s+(.+?)\s*$/.exec(raw.trim());
    if (match2 !== null) {
      current = match2[1] ?? "";
      if (!sections.has(current)) sections.set(current, []);
      continue;
    }
    if (current !== null) sections.get(current)?.push(raw);
  }
  return sections;
}
function isCitationEntryLine(line) {
  return line.startsWith("- ") || line.startsWith("* ") || line.startsWith("+ ") || line.startsWith("|") || /[`]/.test(line);
}
function citationCandidates(line) {
  const backticked = [...line.matchAll(/`([^`]+)`/g)].map((match2) => match2[1] ?? "").filter((span) => colonCount(span) >= 3);
  if (backticked.length > 0) return backticked;
  const tokens = [];
  for (const token of line.split(/\s+/)) {
    if (colonCount(token) >= 3) tokens.push(token);
  }
  return tokens;
}
function colonCount(value) {
  let count2 = 0;
  for (const char of value) if (char === ":") count2 += 1;
  return count2;
}
function scanCitations(text) {
  const found = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed === "") continue;
    for (const candidate of citationCandidates(trimmed)) {
      if (parseCitation(candidate) !== null) found.push(candidate);
    }
  }
  return found;
}
function collectCitations(lines) {
  const citations = [];
  const unparseable = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "" || trimmed.startsWith("###") || /^\|[-:\s|]+\|$/.test(trimmed)) continue;
    const candidates = citationCandidates(trimmed);
    if (candidates.length === 0) {
      if (isCitationEntryLine(trimmed)) unparseable.push(trimmed);
      continue;
    }
    for (const candidate of candidates) {
      if (parseCitation(candidate) === null) unparseable.push(candidate);
      else citations.push(candidate);
    }
  }
  return { citations, unparseable };
}
function validateResearchDoc(keyDir) {
  const findings = [];
  const docs = listResearchDocs(keyDir);
  const named = docs.filter((doc) => path8.basename(doc, ".md").includes("-"));
  const docPath = named[0] ?? docs[0] ?? null;
  if (docPath === null) {
    findings.push("no research document at rag/<server>-<slug>.md");
    return {
      ok: false,
      docPath: null,
      headings: [],
      missingSections: [...RESEARCH_DOC_SECTIONS],
      citations: [],
      unparseable: [],
      hasDoubleColon: false,
      findings
    };
  }
  if (!named.includes(docPath)) {
    findings.push(`research doc '${path8.basename(docPath)}' does not match <server>-<slug>.md`);
  }
  const sections = splitResearchDocSections(fs6.readFileSync(docPath, "utf8"));
  const headings = [];
  const missingSections = [];
  for (const section of RESEARCH_DOC_SECTIONS) {
    if (sections.has(section)) headings.push(`## ${section}`);
    else missingSections.push(section);
  }
  if (missingSections.length > 0) {
    findings.push(`missing section(s): ${missingSections.map((section) => `## ${section}`).join(", ")}`);
  }
  const { citations, unparseable } = collectCitations(sections.get("\u5F15\u7528") ?? []);
  if (citations.length === 0 && unparseable.length === 0) {
    findings.push("## \u5F15\u7528 has no citation entry");
  }
  if (unparseable.length > 0) {
    findings.push(`citation(s) not parseable under server:source:file_path:line: ${unparseable.join(", ")}`);
  }
  const hasDoubleColon = citations.some((citation) => (parseCitation(citation)?.filePath ?? "").includes("::"));
  if (citations.length > 0 && !hasDoubleColon) {
    findings.push("no citation carries the '::' role-prefixed file_path shape");
  }
  return {
    ok: named.includes(docPath) && missingSections.length === 0 && citations.length > 0 && unparseable.length === 0 && hasDoubleColon,
    docPath,
    headings,
    missingSections,
    citations,
    unparseable,
    hasDoubleColon,
    findings
  };
}
function researchDocEvidence(report, role, phase, server) {
  return report.ok ? null : ragRequiredMissingLine({ role, phase, server });
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts
import * as fs7 from "node:fs";
import * as os from "node:os";
import * as path9 from "node:path";
var PROVIDER_ID_TO_PREFIX = {
  timi: "timi",
  anthropic: "claude",
  "openai-codex": "codex",
  deepseek: "deepseek",
  "zai-coding-cn": "zai"
};
var PREFIX_TO_PROVIDER_ID = Object.fromEntries(
  Object.entries(PROVIDER_ID_TO_PREFIX).map(([provider, prefix]) => [prefix, provider])
);
function parseModelValue(value) {
  const idx = value.indexOf("/");
  if (idx < 0) return { prefix: "", modelId: value.trim() };
  return { prefix: value.slice(0, idx).trim(), modelId: value.slice(idx + 1).trim() };
}
function windowModelPath(cwd) {
  return path9.join(cwd, ".mw", "window-model");
}
var DISPATCH_ROLE_BY_TYPE = {
  coding: "coding",
  "phase-writer": "coding",
  repair: "coding",
  "roadmap-writer": "coding",
  review: "review",
  verifier: "review",
  reviewer: "review",
  research: "research",
  "rag-research": "research"
};
var DISPATCHABLE_TYPES = ["coding", "review", "research", "rag-research"];
function roleForTaskType(taskType) {
  return DISPATCH_ROLE_BY_TYPE[taskType] ?? "coding";
}
var CLI_EXECUTOR_PREFIXES = ["codex_cli", "claude_cli"];
function dispatchYmlPath(cwd) {
  return path9.join(cwd, ".mw", "dispatch.yml");
}
function isFrameworkProject(cwd) {
  return fs7.existsSync(path9.join(cwd, ".agenticdoc"));
}
function recordWindowModel(cwd, model) {
  if (!model || !isFrameworkProject(cwd)) return;
  const prefix = PROVIDER_ID_TO_PREFIX[model.provider];
  if (!prefix) return;
  try {
    fs7.mkdirSync(path9.join(cwd, ".mw"), { recursive: true });
    fs7.writeFileSync(windowModelPath(cwd), `${prefix}/${model.id}
`, "utf8");
  } catch {
  }
}
function readRoleModel(cwd, role) {
  let text;
  try {
    text = fs7.readFileSync(dispatchYmlPath(cwd), "utf8");
  } catch {
    return null;
  }
  if (text.charCodeAt(0) === 65279) text = text.slice(1);
  let inModels = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (/^models:\s*$/.test(line)) {
      inModels = true;
      continue;
    }
    if (inModels) {
      if (line && !/^\s/.test(line)) break;
      const m = /^\s+([A-Za-z0-9_-]+):\s*(\S+)\s*$/.exec(line);
      if (m && m[1] === role) return m[2];
    }
  }
  return null;
}
function readMainModelConfig(cwd) {
  return readRoleModel(cwd, "main");
}
function validateModelValue(registry, cli, taskProvider, value) {
  const trimmed = value.trim();
  if (!trimmed || !registry || cli.toLowerCase() !== "pi") return { ok: true, message: "" };
  const { prefix, modelId } = parseModelValue(trimmed);
  if (!modelId) return { ok: false, message: `Model value '${trimmed}' carries no model id.` };
  if (CLI_EXECUTOR_PREFIXES.includes(prefix)) return { ok: true, message: "" };
  const provider = prefix ? PREFIX_TO_PROVIDER_ID[prefix] : taskProvider.trim();
  if (prefix && !provider) {
    const known = [...Object.keys(PREFIX_TO_PROVIDER_ID), ...CLI_EXECUTOR_PREFIXES].sort().join(", ");
    return { ok: false, message: `Model value '${trimmed}' has unknown prefix '${prefix}' (valid: ${known}).` };
  }
  if (!provider) return { ok: true, message: "" };
  const ids = registry.getAll().filter((m) => m.provider === provider).map((m) => m.id);
  if (ids.length === 0) return { ok: true, message: "" };
  if (registry.find(provider, modelId)) return { ok: true, message: "" };
  const candidates = [...new Set(ids)].sort().slice(0, 5).join(", ");
  return {
    ok: false,
    message: `Model '${trimmed}' not found for provider '${provider}' (known ids include: ${candidates}). Use /mw model set <role> ${trimmed} with a valid id, or omit the model to inherit the configured role default.`
  };
}
function settingsDefaultModel() {
  const base = process.env.PI_CODING_AGENT_DIR ?? path9.join(os.homedir(), ".pi", "agent");
  try {
    const settings2 = JSON.parse(fs7.readFileSync(path9.join(base, "settings.json"), "utf8"));
    return typeof settings2.defaultModel === "string" && settings2.defaultModel ? settings2.defaultModel : null;
  } catch {
    return null;
  }
}
function hasCliModelFlag() {
  return process.argv.some((a) => a === "--model" || a.startsWith("--model="));
}
async function applyMainModelConfig(pi, ctx) {
  if (hasCliModelFlag() || settingsDefaultModel()) return;
  const value = readMainModelConfig(ctx.cwd);
  if (!value) return;
  const { prefix, modelId } = parseModelValue(value);
  if (!prefix || !modelId) return;
  const provider = PREFIX_TO_PROVIDER_ID[prefix];
  if (!provider) return;
  const model = ctx.modelRegistry.find(provider, modelId);
  if (!model) {
    ctx.ui.notify(
      `dispatch.yml main=${value} not found in the model registry \u2014 leaving the window model unchanged`,
      "error"
    );
    return;
  }
  if (ctx.model?.provider === model.provider && ctx.model?.id === model.id) return;
  const ok = await pi.setModel(model);
  if (ok) {
    ctx.ui.notify(`model set to ${value} (dispatch.yml main)`, "info");
  }
}
function registerMainWindowModel(pi) {
  pi.on("session_start", (_event, ctx) => {
    recordWindowModel(ctx.cwd, ctx.model);
    void applyMainModelConfig(pi, ctx);
  });
  pi.on("model_select", (event) => {
    recordWindowModel(process.cwd(), event.model);
  });
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/heartbeat.ts
import * as fs8 from "node:fs";
import * as path10 from "node:path";
var HEARTBEAT_INTERVAL_MS = 3e4;
var HEARTBEAT_STALE_MS = 9e4;
var HEARTBEAT_LINE_RE = /^\[HEARTBEAT\] (\S+) task=(\S+)(?: phase=(\S+))?$/;
var START_LINE_RE = /^\[START\] (\S+) task=\S+ type=\S+ phases=(\S+)$/;
var MODEL_LINE_RE = /^\[MODEL\] (\S+) model=(\S+)$/;
var END_LINE_RE = /^\[END\] (\S+) exit=(\d+) elapsed=(\d+)s tools=(\d+) phases=(\S+)$/;
var TOOL_LINE_RE = /^\[TOOL\] (\S+) (\S+)(?: (.*))?$/;
var CHECKPOINT_LINE_RE = /^\[CHECKPOINT\] (\S+) elapsed=(\d+)s reads=(\d+) writes=(\d+) phases=(\S+) uniq_targets=(\d+) repeat_top=(\d+) risk=(low|mid|high)$/;
function formatHeartbeatAge(ms) {
  const s = Math.max(0, Math.round(ms / 1e3));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}
function readTaskProgress(taskDir) {
  let content;
  try {
    content = fs8.readFileSync(path10.join(taskDir, "trace.log"), "utf8");
  } catch {
    return void 0;
  }
  let hbFirstTs = "";
  let hbLastTs = "";
  let hbCount = 0;
  let phase = "-";
  let phaseTotal = "-";
  let startTs;
  let endTs;
  let exitCode;
  let endPhases;
  let lastAction;
  let checkpoint;
  let model;
  for (const line of content.split("\n")) {
    const hb = HEARTBEAT_LINE_RE.exec(line);
    if (hb) {
      hbCount++;
      if (!hbFirstTs) hbFirstTs = hb[1] ?? "";
      hbLastTs = hb[1] ?? "";
      const label = hb[3] ?? "-";
      if (label === "-") {
        phase = "-";
        phaseTotal = "-";
      } else {
        const [p, t] = label.split("/");
        phase = p ?? "-";
        phaseTotal = t ?? "-";
      }
      continue;
    }
    const start = START_LINE_RE.exec(line);
    if (start) {
      startTs = start[1] ?? "";
      continue;
    }
    const mdl = MODEL_LINE_RE.exec(line);
    if (mdl) {
      model = mdl[2] ?? void 0;
      continue;
    }
    const end = END_LINE_RE.exec(line);
    if (end) {
      endTs = end[1] ?? "";
      const code = Number(end[2]);
      if (Number.isInteger(code)) exitCode = code;
      endPhases = end[5] ?? "-";
      continue;
    }
    const tool = TOOL_LINE_RE.exec(line);
    if (tool) {
      lastAction = [tool[2], tool[3]].filter(Boolean).join(" ");
      continue;
    }
    const ck = CHECKPOINT_LINE_RE.exec(line);
    if (ck) {
      checkpoint = {
        ts: ck[1] ?? "",
        elapsedS: Number(ck[2]),
        reads: Number(ck[3]),
        writes: Number(ck[4]),
        phases: ck[5] ?? "-",
        uniqTargets: Number(ck[6]),
        repeatTop: Number(ck[7]),
        risk: ck[8] ?? "low"
      };
    }
  }
  const heartbeat = hbCount > 0 ? {
    lastTs: hbLastTs,
    ageMs: Date.now() - Date.parse(hbLastTs),
    phase,
    phaseTotal,
    count: hbCount,
    firstTs: hbFirstTs
  } : void 0;
  let elapsedMs;
  if (startTs) {
    const end = endTs ? Date.parse(endTs) : Date.now();
    elapsedMs = Math.max(0, end - Date.parse(startTs));
  }
  return { heartbeat, startTs, endTs, exitCode, endPhases, elapsedMs, lastAction, checkpoint, model };
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/paths.ts
import * as path11 from "node:path";
var AGENTICDOC_DIR = ".agenticdoc";
var GOAL_FILE = "goal.md";
var SCRATCH_WORKERS_KEY = "_scratch";
var WORKERS_DIR = "workers";
function agenticdocRoot(projectDir) {
  return path11.join(projectDir, AGENTICDOC_DIR);
}
function goalPath(agenticdocRoot2) {
  return path11.join(agenticdocRoot2, GOAL_FILE);
}
function workersDirFor(agenticdocRoot2, ownerKey) {
  return path11.join(agenticdocRoot2, ownerKey, WORKERS_DIR);
}
function workerTaskDir(agenticdocRoot2, ownerKey, taskKey) {
  return path11.join(workersDirFor(agenticdocRoot2, ownerKey), taskKey);
}
function controlRootFromTaskPath(taskPath) {
  const workersDir = path11.dirname(path11.dirname(taskPath));
  const agenticdocRoot2 = path11.dirname(path11.dirname(workersDir));
  return path11.dirname(agenticdocRoot2);
}

// packages/coding-agent/src/extensions/agent-team-loop/worker/phase-runner.ts
import * as fs9 from "node:fs";
import * as path12 from "node:path";
function goalMtime(agenticdocRoot2) {
  const goalPathResolved = goalPath(agenticdocRoot2);
  try {
    return fs9.statSync(goalPathResolved).mtimeMs;
  } catch {
    return 0;
  }
}
function writePhaseFile(taskKey, agenticdocRoot2, phaseIndex, summary) {
  const progressDir = path12.join(agenticdocRoot2, taskKey, "progress");
  fs9.mkdirSync(progressDir, { recursive: true });
  const content = `# Phase ${phaseIndex + 1}

${summary || "(phase complete)"}
`;
  fs9.writeFileSync(path12.join(progressDir, `phase-${phaseIndex + 1}.md`), content, "utf8");
}

// packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts
import * as fs10 from "node:fs";
import * as path14 from "node:path";

// node_modules/balanced-match/dist/esm/index.js
var balanced = (a, b, str) => {
  const ma = a instanceof RegExp ? maybeMatch(a, str) : a;
  const mb = b instanceof RegExp ? maybeMatch(b, str) : b;
  const r = ma !== null && mb != null && range(ma, mb, str);
  return r && {
    start: r[0],
    end: r[1],
    pre: str.slice(0, r[0]),
    body: str.slice(r[0] + ma.length, r[1]),
    post: str.slice(r[1] + mb.length)
  };
};
var maybeMatch = (reg, str) => {
  const m = str.match(reg);
  return m ? m[0] : null;
};
var range = (a, b, str) => {
  let begs, beg, left, right = void 0, result;
  let ai = str.indexOf(a);
  let bi = str.indexOf(b, ai + 1);
  let i = ai;
  if (ai >= 0 && bi > 0) {
    if (a === b) {
      return [ai, bi];
    }
    begs = [];
    left = str.length;
    while (i >= 0 && !result) {
      if (i === ai) {
        begs.push(i);
        ai = str.indexOf(a, i + 1);
      } else if (begs.length === 1) {
        const r = begs.pop();
        if (r !== void 0)
          result = [r, bi];
      } else {
        beg = begs.pop();
        if (beg !== void 0 && beg < left) {
          left = beg;
          right = bi;
        }
        bi = str.indexOf(b, i + 1);
      }
      i = ai < bi && ai >= 0 ? ai : bi;
    }
    if (begs.length && right !== void 0) {
      result = [left, right];
    }
  }
  return result;
};

// node_modules/brace-expansion/dist/esm/index.js
var escSlash = "\0SLASH" + Math.random() + "\0";
var escOpen = "\0OPEN" + Math.random() + "\0";
var escClose = "\0CLOSE" + Math.random() + "\0";
var escComma = "\0COMMA" + Math.random() + "\0";
var escPeriod = "\0PERIOD" + Math.random() + "\0";
var escSlashPattern = new RegExp(escSlash, "g");
var escOpenPattern = new RegExp(escOpen, "g");
var escClosePattern = new RegExp(escClose, "g");
var escCommaPattern = new RegExp(escComma, "g");
var escPeriodPattern = new RegExp(escPeriod, "g");
var slashPattern = /\\\\/g;
var openPattern = /\\{/g;
var closePattern = /\\}/g;
var commaPattern = /\\,/g;
var periodPattern = /\\\./g;
var EXPANSION_MAX = 1e5;
var EXPANSION_MAX_LENGTH = 4e6;
function numeric(str) {
  return !isNaN(str) ? parseInt(str, 10) : str.charCodeAt(0);
}
function escapeBraces(str) {
  return str.replace(slashPattern, escSlash).replace(openPattern, escOpen).replace(closePattern, escClose).replace(commaPattern, escComma).replace(periodPattern, escPeriod);
}
function unescapeBraces(str) {
  return str.replace(escSlashPattern, "\\").replace(escOpenPattern, "{").replace(escClosePattern, "}").replace(escCommaPattern, ",").replace(escPeriodPattern, ".");
}
function parseCommaParts(str) {
  if (!str) {
    return [""];
  }
  const parts = [];
  const m = balanced("{", "}", str);
  if (!m) {
    return str.split(",");
  }
  const { pre, body, post } = m;
  const p = pre.split(",");
  p[p.length - 1] += "{" + body + "}";
  const postParts = parseCommaParts(post);
  if (post.length) {
    ;
    p[p.length - 1] += postParts.shift();
    p.push.apply(p, postParts);
  }
  parts.push.apply(parts, p);
  return parts;
}
function expand(str, options = {}) {
  if (!str) {
    return [];
  }
  const { max = EXPANSION_MAX, maxLength = EXPANSION_MAX_LENGTH } = options;
  if (str.slice(0, 2) === "{}") {
    str = "\\{\\}" + str.slice(2);
  }
  return expand_(escapeBraces(str), max, maxLength, true).map(unescapeBraces);
}
function embrace(str) {
  return "{" + str + "}";
}
function isPadded(el) {
  return /^-?0\d/.test(el);
}
function lte(i, y) {
  return i <= y;
}
function gte(i, y) {
  return i >= y;
}
function combine(acc, pre, values, max, maxLength, dropEmpties) {
  const out = [];
  let length = 0;
  for (let a = 0; a < acc.length; a++) {
    for (let v = 0; v < values.length; v++) {
      if (out.length >= max)
        return out;
      const expansion = acc[a] + pre + values[v];
      if (dropEmpties && !expansion)
        continue;
      if (length + expansion.length > maxLength)
        return out;
      out.push(expansion);
      length += expansion.length;
    }
  }
  return out;
}
function expandSequence(body, isAlphaSequence, max, maxLength) {
  const n = body.split(/\.\./);
  const N = [];
  if (n[0] === void 0 || n[1] === void 0) {
    return N;
  }
  const x = numeric(n[0]);
  const y = numeric(n[1]);
  const width = Math.max(n[0].length, n[1].length);
  let incr = n.length === 3 && n[2] !== void 0 ? Math.max(Math.abs(numeric(n[2])), 1) : 1;
  let test = lte;
  const reverse = y < x;
  if (reverse) {
    incr *= -1;
    test = gte;
  }
  const pad = n.some(isPadded);
  let length = 0;
  for (let i = x; test(i, y) && N.length < max; i += incr) {
    let c;
    if (isAlphaSequence) {
      c = String.fromCharCode(i);
      if (c === "\\") {
        c = "";
      }
    } else {
      c = String(i);
      if (pad) {
        const need = width - c.length;
        if (need > 0) {
          const z = new Array(need + 1).join("0");
          if (i < 0) {
            c = "-" + z + c.slice(1);
          } else {
            c = z + c;
          }
        }
      }
    }
    if (length + c.length > maxLength)
      break;
    N.push(c);
    length += c.length;
  }
  return N;
}
function expand_(str, max, maxLength, isTop) {
  let acc = [""];
  let dropEmpties = false;
  let firstGroup = true;
  for (; ; ) {
    const m = balanced("{", "}", str);
    if (!m) {
      return combine(acc, str, [""], max, maxLength, dropEmpties);
    }
    const pre = m.pre;
    if (/\$$/.test(pre)) {
      acc = combine(acc, pre + "{" + m.body + "}", [""], max, maxLength, dropEmpties && !m.post.length);
      firstGroup = false;
      if (!m.post.length)
        break;
      str = m.post;
      continue;
    }
    const isNumericSequence = /^-?\d+\.\.-?\d+(?:\.\.-?\d+)?$/.test(m.body);
    const isAlphaSequence = /^[a-zA-Z]\.\.[a-zA-Z](?:\.\.-?\d+)?$/.test(m.body);
    const isSequence = isNumericSequence || isAlphaSequence;
    const isOptions = m.body.indexOf(",") >= 0;
    if (!isSequence && !isOptions) {
      if (m.post.match(/,(?!,).*\}/)) {
        str = m.pre + "{" + m.body + escClose + m.post;
        isTop = true;
        continue;
      }
      return combine(acc, pre + "{" + m.body + "}" + m.post, [""], max, maxLength, dropEmpties);
    }
    if (firstGroup) {
      dropEmpties = isTop && !isSequence;
      firstGroup = false;
    }
    let values;
    if (isSequence) {
      values = expandSequence(m.body, isAlphaSequence, max, maxLength);
    } else {
      let n = parseCommaParts(m.body);
      if (n.length === 1 && n[0] !== void 0) {
        n = expand_(n[0], max, maxLength, false).map(embrace);
        if (n.length === 1) {
          acc = combine(acc, pre + n[0], [""], max, maxLength, dropEmpties && !m.post.length);
          if (!m.post.length)
            break;
          str = m.post;
          continue;
        }
      }
      let dropsEmpties = dropEmpties && !m.post.length && !pre;
      for (let d = 0; dropsEmpties && d < acc.length; d++) {
        if (acc[d]) {
          dropsEmpties = false;
        }
      }
      values = [];
      let valuesLength = 0;
      outer: for (let j = 0; j < n.length; j++) {
        const expanded = expand_(n[j], max, maxLength, false);
        for (let k = 0; k < expanded.length; k++) {
          const v = expanded[k];
          if (dropsEmpties && !v)
            continue;
          if (values.length >= max || valuesLength + v.length > maxLength) {
            break outer;
          }
          values.push(v);
          valuesLength += v.length;
        }
      }
    }
    acc = combine(acc, pre, values, max, maxLength, dropEmpties && !m.post.length);
    if (!m.post.length)
      break;
    str = m.post;
  }
  return acc;
}

// node_modules/minimatch/dist/esm/assert-valid-pattern.js
var MAX_PATTERN_LENGTH = 1024 * 64;
var assertValidPattern = (pattern) => {
  if (typeof pattern !== "string") {
    throw new TypeError("invalid pattern");
  }
  if (pattern.length > MAX_PATTERN_LENGTH) {
    throw new TypeError("pattern is too long");
  }
};

// node_modules/minimatch/dist/esm/brace-expressions.js
var posixClasses = {
  "[:alnum:]": ["\\p{L}\\p{Nl}\\p{Nd}", true],
  "[:alpha:]": ["\\p{L}\\p{Nl}", true],
  "[:ascii:]": ["\\x00-\\x7f", false],
  "[:blank:]": ["\\p{Zs}\\t", true],
  "[:cntrl:]": ["\\p{Cc}", true],
  "[:digit:]": ["\\p{Nd}", true],
  "[:graph:]": ["\\p{Z}\\p{C}", true, true],
  "[:lower:]": ["\\p{Ll}", true],
  "[:print:]": ["\\p{C}", true],
  "[:punct:]": ["\\p{P}", true],
  "[:space:]": ["\\p{Z}\\t\\r\\n\\v\\f", true],
  "[:upper:]": ["\\p{Lu}", true],
  "[:word:]": ["\\p{L}\\p{Nl}\\p{Nd}\\p{Pc}", true],
  "[:xdigit:]": ["A-Fa-f0-9", false]
};
var braceEscape = (s) => s.replace(/[[\]\\-]/g, "\\$&");
var regexpEscape = (s) => s.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&");
var rangesToString = (ranges) => ranges.join("");
var parseClass = (glob, position) => {
  const pos = position;
  if (glob.charAt(pos) !== "[") {
    throw new Error("not in a brace expression");
  }
  const ranges = [];
  const negs = [];
  let i = pos + 1;
  let sawStart = false;
  let uflag = false;
  let escaping = false;
  let negate = false;
  let endPos = pos;
  let rangeStart = "";
  WHILE: while (i < glob.length) {
    const c = glob.charAt(i);
    if ((c === "!" || c === "^") && i === pos + 1) {
      negate = true;
      i++;
      continue;
    }
    if (c === "]" && sawStart && !escaping) {
      endPos = i + 1;
      break;
    }
    sawStart = true;
    if (c === "\\") {
      if (!escaping) {
        escaping = true;
        i++;
        continue;
      }
    }
    if (c === "[" && !escaping) {
      for (const [cls, [unip, u, neg]] of Object.entries(posixClasses)) {
        if (glob.startsWith(cls, i)) {
          if (rangeStart) {
            return ["$.", false, glob.length - pos, true];
          }
          i += cls.length;
          if (neg)
            negs.push(unip);
          else
            ranges.push(unip);
          uflag = uflag || u;
          continue WHILE;
        }
      }
    }
    escaping = false;
    if (rangeStart) {
      if (c > rangeStart) {
        ranges.push(braceEscape(rangeStart) + "-" + braceEscape(c));
      } else if (c === rangeStart) {
        ranges.push(braceEscape(c));
      }
      rangeStart = "";
      i++;
      continue;
    }
    if (glob.startsWith("-]", i + 1)) {
      ranges.push(braceEscape(c + "-"));
      i += 2;
      continue;
    }
    if (glob.startsWith("-", i + 1)) {
      rangeStart = c;
      i += 2;
      continue;
    }
    ranges.push(braceEscape(c));
    i++;
  }
  if (endPos < i) {
    return ["", false, 0, false];
  }
  if (!ranges.length && !negs.length) {
    return ["$.", false, glob.length - pos, true];
  }
  if (negs.length === 0 && ranges.length === 1 && /^\\?.$/.test(ranges[0]) && !negate) {
    const r = ranges[0].length === 2 ? ranges[0].slice(-1) : ranges[0];
    return [regexpEscape(r), false, endPos - pos, false];
  }
  const sranges = "[" + (negate ? "^" : "") + rangesToString(ranges) + "]";
  const snegs = "[" + (negate ? "" : "^") + rangesToString(negs) + "]";
  const comb = ranges.length && negs.length ? "(" + sranges + "|" + snegs + ")" : ranges.length ? sranges : snegs;
  return [comb, uflag, endPos - pos, true];
};

// node_modules/minimatch/dist/esm/unescape.js
var unescape = (s, { windowsPathsNoEscape = false, magicalBraces = true } = {}) => {
  if (magicalBraces) {
    return windowsPathsNoEscape ? s.replace(/\[([^/\\])\]/g, "$1") : s.replace(/((?!\\).|^)\[([^/\\])\]/g, "$1$2").replace(/\\([^/])/g, "$1");
  }
  return windowsPathsNoEscape ? s.replace(/\[([^/\\{}])\]/g, "$1") : s.replace(/((?!\\).|^)\[([^/\\{}])\]/g, "$1$2").replace(/\\([^/{}])/g, "$1");
};

// node_modules/minimatch/dist/esm/ast.js
var _a;
var types = /* @__PURE__ */ new Set(["!", "?", "+", "*", "@"]);
var isExtglobType = (c) => types.has(c);
var isExtglobAST = (c) => isExtglobType(c.type);
var adoptionMap = /* @__PURE__ */ new Map([
  ["!", ["@"]],
  ["?", ["?", "@"]],
  ["@", ["@"]],
  ["*", ["*", "+", "?", "@"]],
  ["+", ["+", "@"]]
]);
var adoptionWithSpaceMap = /* @__PURE__ */ new Map([
  ["!", ["?"]],
  ["@", ["?"]],
  ["+", ["?", "*"]]
]);
var adoptionAnyMap = /* @__PURE__ */ new Map([
  ["!", ["?", "@"]],
  ["?", ["?", "@"]],
  ["@", ["?", "@"]],
  ["*", ["*", "+", "?", "@"]],
  ["+", ["+", "@", "?", "*"]]
]);
var usurpMap = /* @__PURE__ */ new Map([
  ["!", /* @__PURE__ */ new Map([["!", "@"]])],
  [
    "?",
    /* @__PURE__ */ new Map([
      ["*", "*"],
      ["+", "*"]
    ])
  ],
  [
    "@",
    /* @__PURE__ */ new Map([
      ["!", "!"],
      ["?", "?"],
      ["@", "@"],
      ["*", "*"],
      ["+", "+"]
    ])
  ],
  [
    "+",
    /* @__PURE__ */ new Map([
      ["?", "*"],
      ["*", "*"]
    ])
  ]
]);
var startNoTraversal = "(?!(?:^|/)\\.\\.?(?:$|/))";
var startNoDot = "(?!\\.)";
var addPatternStart = /* @__PURE__ */ new Set(["[", "."]);
var justDots = /* @__PURE__ */ new Set(["..", "."]);
var reSpecials = new Set("().*{}+?[]^$\\!");
var regExpEscape = (s) => s.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&");
var qmark = "[^/]";
var star = qmark + "*?";
var starNoEmpty = qmark + "+?";
var ID = 0;
var AST = class {
  type;
  #root;
  #hasMagic;
  #uflag = false;
  #parts = [];
  #parent;
  #parentIndex;
  #negs;
  #filledNegs = false;
  #options;
  #toString;
  // set to true if it's an extglob with no children
  // (which really means one child of '')
  #emptyExt = false;
  id = ++ID;
  get depth() {
    return (this.#parent?.depth ?? -1) + 1;
  }
  [/* @__PURE__ */ Symbol.for("nodejs.util.inspect.custom")]() {
    return {
      "@@type": "AST",
      id: this.id,
      type: this.type,
      root: this.#root.id,
      parent: this.#parent?.id,
      depth: this.depth,
      partsLength: this.#parts.length,
      parts: this.#parts
    };
  }
  constructor(type, parent, options = {}) {
    this.type = type;
    if (type)
      this.#hasMagic = true;
    this.#parent = parent;
    this.#root = this.#parent ? this.#parent.#root : this;
    this.#options = this.#root === this ? options : this.#root.#options;
    this.#negs = this.#root === this ? [] : this.#root.#negs;
    if (type === "!" && !this.#root.#filledNegs)
      this.#negs.push(this);
    this.#parentIndex = this.#parent ? this.#parent.#parts.length : 0;
  }
  get hasMagic() {
    if (this.#hasMagic !== void 0)
      return this.#hasMagic;
    for (const p of this.#parts) {
      if (typeof p === "string")
        continue;
      if (p.type || p.hasMagic)
        return this.#hasMagic = true;
    }
    return this.#hasMagic;
  }
  // reconstructs the pattern
  toString() {
    return this.#toString !== void 0 ? this.#toString : !this.type ? this.#toString = this.#parts.map((p) => String(p)).join("") : this.#toString = this.type + "(" + this.#parts.map((p) => String(p)).join("|") + ")";
  }
  #fillNegs() {
    if (this !== this.#root)
      throw new Error("should only call on root");
    if (this.#filledNegs)
      return this;
    this.toString();
    this.#filledNegs = true;
    let n;
    while (n = this.#negs.pop()) {
      if (n.type !== "!")
        continue;
      let p = n;
      let pp = p.#parent;
      while (pp) {
        for (let i = p.#parentIndex + 1; !pp.type && i < pp.#parts.length; i++) {
          for (const part of n.#parts) {
            if (typeof part === "string") {
              throw new Error("string part in extglob AST??");
            }
            part.copyIn(pp.#parts[i]);
          }
        }
        p = pp;
        pp = p.#parent;
      }
    }
    return this;
  }
  push(...parts) {
    for (const p of parts) {
      if (p === "")
        continue;
      if (typeof p !== "string" && !(p instanceof _a && p.#parent === this)) {
        throw new Error("invalid part: " + p);
      }
      this.#parts.push(p);
    }
  }
  toJSON() {
    const ret = this.type === null ? this.#parts.slice().map((p) => typeof p === "string" ? p : p.toJSON()) : [this.type, ...this.#parts.map((p) => p.toJSON())];
    if (this.isStart() && !this.type)
      ret.unshift([]);
    if (this.isEnd() && (this === this.#root || this.#root.#filledNegs && this.#parent?.type === "!")) {
      ret.push({});
    }
    return ret;
  }
  isStart() {
    if (this.#root === this)
      return true;
    if (!this.#parent?.isStart())
      return false;
    if (this.#parentIndex === 0)
      return true;
    const p = this.#parent;
    for (let i = 0; i < this.#parentIndex; i++) {
      const pp = p.#parts[i];
      if (!(pp instanceof _a && pp.type === "!")) {
        return false;
      }
    }
    return true;
  }
  isEnd() {
    if (this.#root === this)
      return true;
    if (this.#parent?.type === "!")
      return true;
    if (!this.#parent?.isEnd())
      return false;
    if (!this.type)
      return this.#parent?.isEnd();
    const pl = this.#parent ? this.#parent.#parts.length : 0;
    return this.#parentIndex === pl - 1;
  }
  copyIn(part) {
    if (typeof part === "string")
      this.push(part);
    else
      this.push(part.clone(this));
  }
  clone(parent) {
    const c = new _a(this.type, parent);
    for (const p of this.#parts) {
      c.copyIn(p);
    }
    return c;
  }
  static #parseAST(str, ast, pos, opt, extDepth) {
    const maxDepth = opt.maxExtglobRecursion ?? 2;
    let escaping = false;
    let inBrace = false;
    let braceStart = -1;
    let braceNeg = false;
    if (ast.type === null) {
      let i2 = pos;
      let acc2 = "";
      while (i2 < str.length) {
        const c = str.charAt(i2++);
        if (escaping || c === "\\") {
          escaping = !escaping;
          acc2 += c;
          continue;
        }
        if (inBrace) {
          if (i2 === braceStart + 1) {
            if (c === "^" || c === "!") {
              braceNeg = true;
            }
          } else if (c === "]" && !(i2 === braceStart + 2 && braceNeg)) {
            inBrace = false;
          }
          acc2 += c;
          continue;
        } else if (c === "[") {
          inBrace = true;
          braceStart = i2;
          braceNeg = false;
          acc2 += c;
          continue;
        }
        const doRecurse = !opt.noext && isExtglobType(c) && str.charAt(i2) === "(" && extDepth <= maxDepth;
        if (doRecurse) {
          ast.push(acc2);
          acc2 = "";
          const ext2 = new _a(c, ast);
          i2 = _a.#parseAST(str, ext2, i2, opt, extDepth + 1);
          ast.push(ext2);
          continue;
        }
        acc2 += c;
      }
      ast.push(acc2);
      return i2;
    }
    let i = pos + 1;
    let part = new _a(null, ast);
    const parts = [];
    let acc = "";
    while (i < str.length) {
      const c = str.charAt(i++);
      if (escaping || c === "\\") {
        escaping = !escaping;
        acc += c;
        continue;
      }
      if (inBrace) {
        if (i === braceStart + 1) {
          if (c === "^" || c === "!") {
            braceNeg = true;
          }
        } else if (c === "]" && !(i === braceStart + 2 && braceNeg)) {
          inBrace = false;
        }
        acc += c;
        continue;
      } else if (c === "[") {
        inBrace = true;
        braceStart = i;
        braceNeg = false;
        acc += c;
        continue;
      }
      const doRecurse = !opt.noext && isExtglobType(c) && str.charAt(i) === "(" && /* c8 ignore start - the maxDepth is sufficient here */
      (extDepth <= maxDepth || ast && ast.#canAdoptType(c));
      if (doRecurse) {
        const depthAdd = ast && ast.#canAdoptType(c) ? 0 : 1;
        part.push(acc);
        acc = "";
        const ext2 = new _a(c, part);
        part.push(ext2);
        i = _a.#parseAST(str, ext2, i, opt, extDepth + depthAdd);
        continue;
      }
      if (c === "|") {
        part.push(acc);
        acc = "";
        parts.push(part);
        part = new _a(null, ast);
        continue;
      }
      if (c === ")") {
        if (acc === "" && ast.#parts.length === 0) {
          ast.#emptyExt = true;
        }
        part.push(acc);
        acc = "";
        ast.push(...parts, part);
        return i;
      }
      acc += c;
    }
    ast.type = null;
    ast.#hasMagic = void 0;
    ast.#parts = [str.substring(pos - 1)];
    return i;
  }
  #canAdoptWithSpace(child) {
    return this.#canAdopt(child, adoptionWithSpaceMap);
  }
  #canAdopt(child, map = adoptionMap) {
    if (!child || typeof child !== "object" || child.type !== null || child.#parts.length !== 1 || this.type === null) {
      return false;
    }
    const gc = child.#parts[0];
    if (!gc || typeof gc !== "object" || gc.type === null) {
      return false;
    }
    return this.#canAdoptType(gc.type, map);
  }
  #canAdoptType(c, map = adoptionAnyMap) {
    return !!map.get(this.type)?.includes(c);
  }
  #adoptWithSpace(child, index) {
    const gc = child.#parts[0];
    const blank = new _a(null, gc, this.options);
    blank.#parts.push("");
    gc.push(blank);
    this.#adopt(child, index);
  }
  #adopt(child, index) {
    const gc = child.#parts[0];
    this.#parts.splice(index, 1, ...gc.#parts);
    for (const p of gc.#parts) {
      if (typeof p === "object")
        p.#parent = this;
    }
    this.#toString = void 0;
  }
  #canUsurpType(c) {
    const m = usurpMap.get(this.type);
    return !!m?.has(c);
  }
  #canUsurp(child) {
    if (!child || typeof child !== "object" || child.type !== null || child.#parts.length !== 1 || this.type === null || this.#parts.length !== 1) {
      return false;
    }
    const gc = child.#parts[0];
    if (!gc || typeof gc !== "object" || gc.type === null) {
      return false;
    }
    return this.#canUsurpType(gc.type);
  }
  #usurp(child) {
    const m = usurpMap.get(this.type);
    const gc = child.#parts[0];
    const nt = m?.get(gc.type);
    if (!nt)
      return false;
    this.#parts = gc.#parts;
    for (const p of this.#parts) {
      if (typeof p === "object") {
        p.#parent = this;
      }
    }
    this.type = nt;
    this.#toString = void 0;
    this.#emptyExt = false;
  }
  static fromGlob(pattern, options = {}) {
    const ast = new _a(null, void 0, options);
    _a.#parseAST(pattern, ast, 0, options, 0);
    return ast;
  }
  // returns the regular expression if there's magic, or the unescaped
  // string if not.
  toMMPattern() {
    if (this !== this.#root)
      return this.#root.toMMPattern();
    const glob = this.toString();
    const [re, body, hasMagic, uflag] = this.toRegExpSource();
    const anyMagic = hasMagic || this.#hasMagic || this.#options.nocase && !this.#options.nocaseMagicOnly && glob.toUpperCase() !== glob.toLowerCase();
    if (!anyMagic) {
      return body;
    }
    const flags = (this.#options.nocase ? "i" : "") + (uflag ? "u" : "");
    return Object.assign(new RegExp(`^${re}$`, flags), {
      _src: re,
      _glob: glob
    });
  }
  get options() {
    return this.#options;
  }
  // returns the string match, the regexp source, whether there's magic
  // in the regexp (so a regular expression is required) and whether or
  // not the uflag is needed for the regular expression (for posix classes)
  // TODO: instead of injecting the start/end at this point, just return
  // the BODY of the regexp, along with the start/end portions suitable
  // for binding the start/end in either a joined full-path makeRe context
  // (where we bind to (^|/), or a standalone matchPart context (where
  // we bind to ^, and not /).  Otherwise slashes get duped!
  //
  // In part-matching mode, the start is:
  // - if not isStart: nothing
  // - if traversal possible, but not allowed: ^(?!\.\.?$)
  // - if dots allowed or not possible: ^
  // - if dots possible and not allowed: ^(?!\.)
  // end is:
  // - if not isEnd(): nothing
  // - else: $
  //
  // In full-path matching mode, we put the slash at the START of the
  // pattern, so start is:
  // - if first pattern: same as part-matching mode
  // - if not isStart(): nothing
  // - if traversal possible, but not allowed: /(?!\.\.?(?:$|/))
  // - if dots allowed or not possible: /
  // - if dots possible and not allowed: /(?!\.)
  // end is:
  // - if last pattern, same as part-matching mode
  // - else nothing
  //
  // Always put the (?:$|/) on negated tails, though, because that has to be
  // there to bind the end of the negated pattern portion, and it's easier to
  // just stick it in now rather than try to inject it later in the middle of
  // the pattern.
  //
  // We can just always return the same end, and leave it up to the caller
  // to know whether it's going to be used joined or in parts.
  // And, if the start is adjusted slightly, can do the same there:
  // - if not isStart: nothing
  // - if traversal possible, but not allowed: (?:/|^)(?!\.\.?$)
  // - if dots allowed or not possible: (?:/|^)
  // - if dots possible and not allowed: (?:/|^)(?!\.)
  //
  // But it's better to have a simpler binding without a conditional, for
  // performance, so probably better to return both start options.
  //
  // Then the caller just ignores the end if it's not the first pattern,
  // and the start always gets applied.
  //
  // But that's always going to be $ if it's the ending pattern, or nothing,
  // so the caller can just attach $ at the end of the pattern when building.
  //
  // So the todo is:
  // - better detect what kind of start is needed
  // - return both flavors of starting pattern
  // - attach $ at the end of the pattern when creating the actual RegExp
  //
  // Ah, but wait, no, that all only applies to the root when the first pattern
  // is not an extglob. If the first pattern IS an extglob, then we need all
  // that dot prevention biz to live in the extglob portions, because eg
  // +(*|.x*) can match .xy but not .yx.
  //
  // So, return the two flavors if it's #root and the first child is not an
  // AST, otherwise leave it to the child AST to handle it, and there,
  // use the (?:^|/) style of start binding.
  //
  // Even simplified further:
  // - Since the start for a join is eg /(?!\.) and the start for a part
  // is ^(?!\.), we can just prepend (?!\.) to the pattern (either root
  // or start or whatever) and prepend ^ or / at the Regexp construction.
  toRegExpSource(allowDot) {
    const dot = allowDot ?? !!this.#options.dot;
    if (this.#root === this) {
      this.#flatten();
      this.#fillNegs();
    }
    if (!isExtglobAST(this)) {
      const noEmpty = this.isStart() && this.isEnd() && !this.#parts.some((s) => typeof s !== "string");
      const src = this.#parts.map((p) => {
        const [re, _, hasMagic, uflag] = typeof p === "string" ? _a.#parseGlob(p, this.#hasMagic, noEmpty) : p.toRegExpSource(allowDot);
        this.#hasMagic = this.#hasMagic || hasMagic;
        this.#uflag = this.#uflag || uflag;
        return re;
      }).join("");
      let start2 = "";
      if (this.isStart()) {
        if (typeof this.#parts[0] === "string") {
          const dotTravAllowed = this.#parts.length === 1 && justDots.has(this.#parts[0]);
          if (!dotTravAllowed) {
            const aps = addPatternStart;
            const needNoTrav = (
              // dots are allowed, and the pattern starts with [ or .
              dot && aps.has(src.charAt(0)) || // the pattern starts with \., and then [ or .
              src.startsWith("\\.") && aps.has(src.charAt(2)) || // the pattern starts with \.\., and then [ or .
              src.startsWith("\\.\\.") && aps.has(src.charAt(4))
            );
            const needNoDot = !dot && !allowDot && aps.has(src.charAt(0));
            start2 = needNoTrav ? startNoTraversal : needNoDot ? startNoDot : "";
          }
        }
      }
      let end = "";
      if (this.isEnd() && this.#root.#filledNegs && this.#parent?.type === "!") {
        end = "(?:$|\\/)";
      }
      const final2 = start2 + src + end;
      return [
        final2,
        unescape(src),
        this.#hasMagic = !!this.#hasMagic,
        this.#uflag
      ];
    }
    const repeated = this.type === "*" || this.type === "+";
    const start = this.type === "!" ? "(?:(?!(?:" : "(?:";
    let body = this.#partsToRegExp(dot);
    if (this.isStart() && this.isEnd() && !body && this.type !== "!") {
      const s = this.toString();
      const me = this;
      me.#parts = [s];
      me.type = null;
      me.#hasMagic = void 0;
      return [s, unescape(this.toString()), false, false];
    }
    let bodyDotAllowed = !repeated || allowDot || dot || !startNoDot ? "" : this.#partsToRegExp(true);
    if (bodyDotAllowed === body) {
      bodyDotAllowed = "";
    }
    if (bodyDotAllowed) {
      body = `(?:${body})(?:${bodyDotAllowed})*?`;
    }
    let final = "";
    if (this.type === "!" && this.#emptyExt) {
      final = (this.isStart() && !dot ? startNoDot : "") + starNoEmpty;
    } else {
      const close = this.type === "!" ? (
        // !() must match something,but !(x) can match ''
        "))" + (this.isStart() && !dot && !allowDot ? startNoDot : "") + star + ")"
      ) : this.type === "@" ? ")" : this.type === "?" ? ")?" : this.type === "+" && bodyDotAllowed ? ")" : this.type === "*" && bodyDotAllowed ? `)?` : `)${this.type}`;
      final = start + body + close;
    }
    return [
      final,
      unescape(body),
      this.#hasMagic = !!this.#hasMagic,
      this.#uflag
    ];
  }
  #flatten() {
    if (!isExtglobAST(this)) {
      for (const p of this.#parts) {
        if (typeof p === "object") {
          p.#flatten();
        }
      }
    } else {
      let iterations = 0;
      let done = false;
      do {
        done = true;
        for (let i = 0; i < this.#parts.length; i++) {
          const c = this.#parts[i];
          if (typeof c === "object") {
            c.#flatten();
            if (this.#canAdopt(c)) {
              done = false;
              this.#adopt(c, i);
            } else if (this.#canAdoptWithSpace(c)) {
              done = false;
              this.#adoptWithSpace(c, i);
            } else if (this.#canUsurp(c)) {
              done = false;
              this.#usurp(c);
            }
          }
        }
      } while (!done && ++iterations < 10);
    }
    this.#toString = void 0;
  }
  #partsToRegExp(dot) {
    return this.#parts.map((p) => {
      if (typeof p === "string") {
        throw new Error("string type in extglob ast??");
      }
      const [re, _, _hasMagic, uflag] = p.toRegExpSource(dot);
      this.#uflag = this.#uflag || uflag;
      return re;
    }).filter((p) => !(this.isStart() && this.isEnd()) || !!p).join("|");
  }
  static #parseGlob(glob, hasMagic, noEmpty = false) {
    let escaping = false;
    let re = "";
    let uflag = false;
    let inStar = false;
    for (let i = 0; i < glob.length; i++) {
      const c = glob.charAt(i);
      if (escaping) {
        escaping = false;
        re += (reSpecials.has(c) ? "\\" : "") + c;
        continue;
      }
      if (c === "*") {
        if (inStar)
          continue;
        inStar = true;
        re += noEmpty && /^[*]+$/.test(glob) ? starNoEmpty : star;
        hasMagic = true;
        continue;
      } else {
        inStar = false;
      }
      if (c === "\\") {
        if (i === glob.length - 1) {
          re += "\\\\";
        } else {
          escaping = true;
        }
        continue;
      }
      if (c === "[") {
        const [src, needUflag, consumed, magic] = parseClass(glob, i);
        if (consumed) {
          re += src;
          uflag = uflag || needUflag;
          i += consumed - 1;
          hasMagic = hasMagic || magic;
          continue;
        }
      }
      if (c === "?") {
        re += qmark;
        hasMagic = true;
        continue;
      }
      re += regExpEscape(c);
    }
    return [re, unescape(glob), !!hasMagic, uflag];
  }
};
_a = AST;

// node_modules/minimatch/dist/esm/escape.js
var escape = (s, { windowsPathsNoEscape = false, magicalBraces = false } = {}) => {
  if (magicalBraces) {
    return windowsPathsNoEscape ? s.replace(/[?*()[\]{}]/g, "[$&]") : s.replace(/[?*()[\]\\{}]/g, "\\$&");
  }
  return windowsPathsNoEscape ? s.replace(/[?*()[\]]/g, "[$&]") : s.replace(/[?*()[\]\\]/g, "\\$&");
};

// node_modules/minimatch/dist/esm/index.js
var minimatch = (p, pattern, options = {}) => {
  assertValidPattern(pattern);
  if (!options.nocomment && pattern.charAt(0) === "#") {
    return false;
  }
  return new Minimatch(pattern, options).match(p);
};
var starDotExtRE = /^\*+([^+@!?*[(]*)$/;
var starDotExtTest = (ext2) => (f) => !f.startsWith(".") && f.endsWith(ext2);
var starDotExtTestDot = (ext2) => (f) => f.endsWith(ext2);
var starDotExtTestNocase = (ext2) => {
  ext2 = ext2.toLowerCase();
  return (f) => !f.startsWith(".") && f.toLowerCase().endsWith(ext2);
};
var starDotExtTestNocaseDot = (ext2) => {
  ext2 = ext2.toLowerCase();
  return (f) => f.toLowerCase().endsWith(ext2);
};
var starDotStarRE = /^\*+\.\*+$/;
var starDotStarTest = (f) => !f.startsWith(".") && f.includes(".");
var starDotStarTestDot = (f) => f !== "." && f !== ".." && f.includes(".");
var dotStarRE = /^\.\*+$/;
var dotStarTest = (f) => f !== "." && f !== ".." && f.startsWith(".");
var starRE = /^\*+$/;
var starTest = (f) => f.length !== 0 && !f.startsWith(".");
var starTestDot = (f) => f.length !== 0 && f !== "." && f !== "..";
var qmarksRE = /^\?+([^+@!?*[(]*)?$/;
var qmarksTestNocase = ([$0, ext2 = ""]) => {
  const noext = qmarksTestNoExt([$0]);
  if (!ext2)
    return noext;
  ext2 = ext2.toLowerCase();
  return (f) => noext(f) && f.toLowerCase().endsWith(ext2);
};
var qmarksTestNocaseDot = ([$0, ext2 = ""]) => {
  const noext = qmarksTestNoExtDot([$0]);
  if (!ext2)
    return noext;
  ext2 = ext2.toLowerCase();
  return (f) => noext(f) && f.toLowerCase().endsWith(ext2);
};
var qmarksTestDot = ([$0, ext2 = ""]) => {
  const noext = qmarksTestNoExtDot([$0]);
  return !ext2 ? noext : (f) => noext(f) && f.endsWith(ext2);
};
var qmarksTest = ([$0, ext2 = ""]) => {
  const noext = qmarksTestNoExt([$0]);
  return !ext2 ? noext : (f) => noext(f) && f.endsWith(ext2);
};
var qmarksTestNoExt = ([$0]) => {
  const len = $0.length;
  return (f) => f.length === len && !f.startsWith(".");
};
var qmarksTestNoExtDot = ([$0]) => {
  const len = $0.length;
  return (f) => f.length === len && f !== "." && f !== "..";
};
var defaultPlatform = typeof process === "object" && process ? typeof process.env === "object" && process.env && process.env.__MINIMATCH_TESTING_PLATFORM__ || process.platform : "posix";
var path13 = {
  win32: { sep: "\\" },
  posix: { sep: "/" }
};
var sep5 = defaultPlatform === "win32" ? path13.win32.sep : path13.posix.sep;
minimatch.sep = sep5;
var GLOBSTAR = /* @__PURE__ */ Symbol("globstar **");
minimatch.GLOBSTAR = GLOBSTAR;
var qmark2 = "[^/]";
var star2 = qmark2 + "*?";
var twoStarDot = "(?:(?!(?:\\/|^)(?:\\.{1,2})($|\\/)).)*?";
var twoStarNoDot = "(?:(?!(?:\\/|^)\\.).)*?";
var filter = (pattern, options = {}) => (p) => minimatch(p, pattern, options);
minimatch.filter = filter;
var ext = (a, b = {}) => Object.assign({}, a, b);
var defaults = (def) => {
  if (!def || typeof def !== "object" || !Object.keys(def).length) {
    return minimatch;
  }
  const orig = minimatch;
  const m = (p, pattern, options = {}) => orig(p, pattern, ext(def, options));
  return Object.assign(m, {
    Minimatch: class Minimatch extends orig.Minimatch {
      constructor(pattern, options = {}) {
        super(pattern, ext(def, options));
      }
      static defaults(options) {
        return orig.defaults(ext(def, options)).Minimatch;
      }
    },
    AST: class AST extends orig.AST {
      /* c8 ignore start */
      constructor(type, parent, options = {}) {
        super(type, parent, ext(def, options));
      }
      /* c8 ignore stop */
      static fromGlob(pattern, options = {}) {
        return orig.AST.fromGlob(pattern, ext(def, options));
      }
    },
    unescape: (s, options = {}) => orig.unescape(s, ext(def, options)),
    escape: (s, options = {}) => orig.escape(s, ext(def, options)),
    filter: (pattern, options = {}) => orig.filter(pattern, ext(def, options)),
    defaults: (options) => orig.defaults(ext(def, options)),
    makeRe: (pattern, options = {}) => orig.makeRe(pattern, ext(def, options)),
    braceExpand: (pattern, options = {}) => orig.braceExpand(pattern, ext(def, options)),
    match: (list, pattern, options = {}) => orig.match(list, pattern, ext(def, options)),
    sep: orig.sep,
    GLOBSTAR
  });
};
minimatch.defaults = defaults;
var braceExpand = (pattern, options = {}) => {
  assertValidPattern(pattern);
  if (options.nobrace || !/\{(?:(?!\{).)*\}/.test(pattern)) {
    return [pattern];
  }
  return expand(pattern, { max: options.braceExpandMax });
};
minimatch.braceExpand = braceExpand;
var makeRe = (pattern, options = {}) => new Minimatch(pattern, options).makeRe();
minimatch.makeRe = makeRe;
var match = (list, pattern, options = {}) => {
  const mm = new Minimatch(pattern, options);
  list = list.filter((f) => mm.match(f));
  if (mm.options.nonull && !list.length) {
    list.push(pattern);
  }
  return list;
};
minimatch.match = match;
var globMagic = /[?*]|[+@!]\(.*?\)|\[|\]/;
var regExpEscape2 = (s) => s.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&");
var Minimatch = class {
  options;
  set;
  pattern;
  windowsPathsNoEscape;
  nonegate;
  negate;
  comment;
  empty;
  preserveMultipleSlashes;
  partial;
  globSet;
  globParts;
  nocase;
  isWindows;
  platform;
  windowsNoMagicRoot;
  maxGlobstarRecursion;
  regexp;
  constructor(pattern, options = {}) {
    assertValidPattern(pattern);
    options = options || {};
    this.options = options;
    this.maxGlobstarRecursion = options.maxGlobstarRecursion ?? 200;
    this.pattern = pattern;
    this.platform = options.platform || defaultPlatform;
    this.isWindows = this.platform === "win32";
    const awe = "allowWindowsEscape";
    this.windowsPathsNoEscape = !!options.windowsPathsNoEscape || options[awe] === false;
    if (this.windowsPathsNoEscape) {
      this.pattern = this.pattern.replace(/\\/g, "/");
    }
    this.preserveMultipleSlashes = !!options.preserveMultipleSlashes;
    this.regexp = null;
    this.negate = false;
    this.nonegate = !!options.nonegate;
    this.comment = false;
    this.empty = false;
    this.partial = !!options.partial;
    this.nocase = !!this.options.nocase;
    this.windowsNoMagicRoot = options.windowsNoMagicRoot !== void 0 ? options.windowsNoMagicRoot : !!(this.isWindows && this.nocase);
    this.globSet = [];
    this.globParts = [];
    this.set = [];
    this.make();
  }
  hasMagic() {
    if (this.options.magicalBraces && this.set.length > 1) {
      return true;
    }
    for (const pattern of this.set) {
      for (const part of pattern) {
        if (typeof part !== "string")
          return true;
      }
    }
    return false;
  }
  debug(..._) {
  }
  make() {
    const pattern = this.pattern;
    const options = this.options;
    if (!options.nocomment && pattern.charAt(0) === "#") {
      this.comment = true;
      return;
    }
    if (!pattern) {
      this.empty = true;
      return;
    }
    this.parseNegate();
    this.globSet = [...new Set(this.braceExpand())];
    if (options.debug) {
      this.debug = (...args) => console.error(...args);
    }
    this.debug(this.pattern, this.globSet);
    const rawGlobParts = this.globSet.map((s) => this.slashSplit(s));
    this.globParts = this.preprocess(rawGlobParts);
    this.debug(this.pattern, this.globParts);
    let set = this.globParts.map((s, _, __) => {
      if (this.isWindows && this.windowsNoMagicRoot) {
        const isUNC = s[0] === "" && s[1] === "" && (s[2] === "?" || !globMagic.test(s[2])) && !globMagic.test(s[3]);
        const isDrive = /^[a-z]:/i.test(s[0]);
        if (isUNC) {
          return [
            ...s.slice(0, 4),
            ...s.slice(4).map((ss) => this.parse(ss))
          ];
        } else if (isDrive) {
          return [s[0], ...s.slice(1).map((ss) => this.parse(ss))];
        }
      }
      return s.map((ss) => this.parse(ss));
    });
    this.debug(this.pattern, set);
    this.set = set.filter((s) => s.indexOf(false) === -1);
    if (this.isWindows) {
      for (let i = 0; i < this.set.length; i++) {
        const p = this.set[i];
        if (p[0] === "" && p[1] === "" && this.globParts[i][2] === "?" && typeof p[3] === "string" && /^[a-z]:$/i.test(p[3])) {
          p[2] = "?";
        }
      }
    }
    this.debug(this.pattern, this.set);
  }
  // various transforms to equivalent pattern sets that are
  // faster to process in a filesystem walk.  The goal is to
  // eliminate what we can, and push all ** patterns as far
  // to the right as possible, even if it increases the number
  // of patterns that we have to process.
  preprocess(globParts) {
    if (this.options.noglobstar) {
      for (const partset of globParts) {
        for (let j = 0; j < partset.length; j++) {
          if (partset[j] === "**") {
            partset[j] = "*";
          }
        }
      }
    }
    const { optimizationLevel = 1 } = this.options;
    if (optimizationLevel >= 2) {
      globParts = this.firstPhasePreProcess(globParts);
      globParts = this.secondPhasePreProcess(globParts);
    } else if (optimizationLevel >= 1) {
      globParts = this.levelOneOptimize(globParts);
    } else {
      globParts = this.adjascentGlobstarOptimize(globParts);
    }
    return globParts;
  }
  // just get rid of adjascent ** portions
  adjascentGlobstarOptimize(globParts) {
    return globParts.map((parts) => {
      let gs = -1;
      while (-1 !== (gs = parts.indexOf("**", gs + 1))) {
        let i = gs;
        while (parts[i + 1] === "**") {
          i++;
        }
        if (i !== gs) {
          parts.splice(gs, i - gs);
        }
      }
      return parts;
    });
  }
  // get rid of adjascent ** and resolve .. portions
  levelOneOptimize(globParts) {
    return globParts.map((parts) => {
      parts = parts.reduce((set, part) => {
        const prev = set[set.length - 1];
        if (part === "**" && prev === "**") {
          return set;
        }
        if (part === "..") {
          if (prev && prev !== ".." && prev !== "." && prev !== "**") {
            set.pop();
            return set;
          }
        }
        set.push(part);
        return set;
      }, []);
      return parts.length === 0 ? [""] : parts;
    });
  }
  levelTwoFileOptimize(parts) {
    if (!Array.isArray(parts)) {
      parts = this.slashSplit(parts);
    }
    let didSomething = false;
    do {
      didSomething = false;
      if (!this.preserveMultipleSlashes) {
        for (let i = 1; i < parts.length - 1; i++) {
          const p = parts[i];
          if (i === 1 && p === "" && parts[0] === "")
            continue;
          if (p === "." || p === "") {
            didSomething = true;
            parts.splice(i, 1);
            i--;
          }
        }
        if (parts[0] === "." && parts.length === 2 && (parts[1] === "." || parts[1] === "")) {
          didSomething = true;
          parts.pop();
        }
      }
      let dd = 0;
      while (-1 !== (dd = parts.indexOf("..", dd + 1))) {
        const p = parts[dd - 1];
        if (p && p !== "." && p !== ".." && p !== "**" && !(this.isWindows && /^[a-z]:$/i.test(p))) {
          didSomething = true;
          parts.splice(dd - 1, 2);
          dd -= 2;
        }
      }
    } while (didSomething);
    return parts.length === 0 ? [""] : parts;
  }
  // First phase: single-pattern processing
  // <pre> is 1 or more portions
  // <rest> is 1 or more portions
  // <p> is any portion other than ., .., '', or **
  // <e> is . or ''
  //
  // **/.. is *brutal* for filesystem walking performance, because
  // it effectively resets the recursive walk each time it occurs,
  // and ** cannot be reduced out by a .. pattern part like a regexp
  // or most strings (other than .., ., and '') can be.
  //
  // <pre>/**/../<p>/<p>/<rest> -> {<pre>/../<p>/<p>/<rest>,<pre>/**/<p>/<p>/<rest>}
  // <pre>/<e>/<rest> -> <pre>/<rest>
  // <pre>/<p>/../<rest> -> <pre>/<rest>
  // **/**/<rest> -> **/<rest>
  //
  // **/*/<rest> -> */**/<rest> <== not valid because ** doesn't follow
  // this WOULD be allowed if ** did follow symlinks, or * didn't
  firstPhasePreProcess(globParts) {
    let didSomething = false;
    do {
      didSomething = false;
      for (let parts of globParts) {
        let gs = -1;
        while (-1 !== (gs = parts.indexOf("**", gs + 1))) {
          let gss = gs;
          while (parts[gss + 1] === "**") {
            gss++;
          }
          if (gss > gs) {
            parts.splice(gs + 1, gss - gs);
          }
          let next = parts[gs + 1];
          const p = parts[gs + 2];
          const p2 = parts[gs + 3];
          if (next !== "..")
            continue;
          if (!p || p === "." || p === ".." || !p2 || p2 === "." || p2 === "..") {
            continue;
          }
          didSomething = true;
          parts.splice(gs, 1);
          const other = parts.slice(0);
          other[gs] = "**";
          globParts.push(other);
          gs--;
        }
        if (!this.preserveMultipleSlashes) {
          for (let i = 1; i < parts.length - 1; i++) {
            const p = parts[i];
            if (i === 1 && p === "" && parts[0] === "")
              continue;
            if (p === "." || p === "") {
              didSomething = true;
              parts.splice(i, 1);
              i--;
            }
          }
          if (parts[0] === "." && parts.length === 2 && (parts[1] === "." || parts[1] === "")) {
            didSomething = true;
            parts.pop();
          }
        }
        let dd = 0;
        while (-1 !== (dd = parts.indexOf("..", dd + 1))) {
          const p = parts[dd - 1];
          if (p && p !== "." && p !== ".." && p !== "**") {
            didSomething = true;
            const needDot = dd === 1 && parts[dd + 1] === "**";
            const splin = needDot ? ["."] : [];
            parts.splice(dd - 1, 2, ...splin);
            if (parts.length === 0)
              parts.push("");
            dd -= 2;
          }
        }
      }
    } while (didSomething);
    return globParts;
  }
  // second phase: multi-pattern dedupes
  // {<pre>/*/<rest>,<pre>/<p>/<rest>} -> <pre>/*/<rest>
  // {<pre>/<rest>,<pre>/<rest>} -> <pre>/<rest>
  // {<pre>/**/<rest>,<pre>/<rest>} -> <pre>/**/<rest>
  //
  // {<pre>/**/<rest>,<pre>/**/<p>/<rest>} -> <pre>/**/<rest>
  // ^-- not valid because ** doens't follow symlinks
  secondPhasePreProcess(globParts) {
    for (let i = 0; i < globParts.length - 1; i++) {
      for (let j = i + 1; j < globParts.length; j++) {
        const matched = this.partsMatch(globParts[i], globParts[j], !this.preserveMultipleSlashes);
        if (matched) {
          globParts[i] = [];
          globParts[j] = matched;
          break;
        }
      }
    }
    return globParts.filter((gs) => gs.length);
  }
  partsMatch(a, b, emptyGSMatch = false) {
    let ai = 0;
    let bi = 0;
    let result = [];
    let which = "";
    while (ai < a.length && bi < b.length) {
      if (a[ai] === b[bi]) {
        result.push(which === "b" ? b[bi] : a[ai]);
        ai++;
        bi++;
      } else if (emptyGSMatch && a[ai] === "**" && b[bi] === a[ai + 1]) {
        result.push(a[ai]);
        ai++;
      } else if (emptyGSMatch && b[bi] === "**" && a[ai] === b[bi + 1]) {
        result.push(b[bi]);
        bi++;
      } else if (a[ai] === "*" && b[bi] && (this.options.dot || !b[bi].startsWith(".")) && b[bi] !== "**") {
        if (which === "b")
          return false;
        which = "a";
        result.push(a[ai]);
        ai++;
        bi++;
      } else if (b[bi] === "*" && a[ai] && (this.options.dot || !a[ai].startsWith(".")) && a[ai] !== "**") {
        if (which === "a")
          return false;
        which = "b";
        result.push(b[bi]);
        ai++;
        bi++;
      } else {
        return false;
      }
    }
    return a.length === b.length && result;
  }
  parseNegate() {
    if (this.nonegate)
      return;
    const pattern = this.pattern;
    let negate = false;
    let negateOffset = 0;
    for (let i = 0; i < pattern.length && pattern.charAt(i) === "!"; i++) {
      negate = !negate;
      negateOffset++;
    }
    if (negateOffset)
      this.pattern = pattern.slice(negateOffset);
    this.negate = negate;
  }
  // set partial to true to test if, for example,
  // "/a/b" matches the start of "/*/b/*/d"
  // Partial means, if you run out of file before you run
  // out of pattern, then that's fine, as long as all
  // the parts match.
  matchOne(file, pattern, partial = false) {
    let fileStartIndex = 0;
    let patternStartIndex = 0;
    if (this.isWindows) {
      const fileDrive = typeof file[0] === "string" && /^[a-z]:$/i.test(file[0]);
      const fileUNC = !fileDrive && file[0] === "" && file[1] === "" && file[2] === "?" && /^[a-z]:$/i.test(file[3]);
      const patternDrive = typeof pattern[0] === "string" && /^[a-z]:$/i.test(pattern[0]);
      const patternUNC = !patternDrive && pattern[0] === "" && pattern[1] === "" && pattern[2] === "?" && typeof pattern[3] === "string" && /^[a-z]:$/i.test(pattern[3]);
      const fdi = fileUNC ? 3 : fileDrive ? 0 : void 0;
      const pdi = patternUNC ? 3 : patternDrive ? 0 : void 0;
      if (typeof fdi === "number" && typeof pdi === "number") {
        const [fd, pd] = [
          file[fdi],
          pattern[pdi]
        ];
        if (fd.toLowerCase() === pd.toLowerCase()) {
          pattern[pdi] = fd;
          patternStartIndex = pdi;
          fileStartIndex = fdi;
        }
      }
    }
    const { optimizationLevel = 1 } = this.options;
    if (optimizationLevel >= 2) {
      file = this.levelTwoFileOptimize(file);
    }
    if (pattern.includes(GLOBSTAR)) {
      return this.#matchGlobstar(file, pattern, partial, fileStartIndex, patternStartIndex);
    }
    return this.#matchOne(file, pattern, partial, fileStartIndex, patternStartIndex);
  }
  #matchGlobstar(file, pattern, partial, fileIndex, patternIndex) {
    const firstgs = pattern.indexOf(GLOBSTAR, patternIndex);
    const lastgs = pattern.lastIndexOf(GLOBSTAR);
    const [head, body, tail] = partial ? [
      pattern.slice(patternIndex, firstgs),
      pattern.slice(firstgs + 1),
      []
    ] : [
      pattern.slice(patternIndex, firstgs),
      pattern.slice(firstgs + 1, lastgs),
      pattern.slice(lastgs + 1)
    ];
    if (head.length) {
      const fileHead = file.slice(fileIndex, fileIndex + head.length);
      if (!this.#matchOne(fileHead, head, partial, 0, 0)) {
        return false;
      }
      fileIndex += head.length;
      patternIndex += head.length;
    }
    let fileTailMatch = 0;
    if (tail.length) {
      if (tail.length + fileIndex > file.length)
        return false;
      let tailStart = file.length - tail.length;
      if (this.#matchOne(file, tail, partial, tailStart, 0)) {
        fileTailMatch = tail.length;
      } else {
        if (file[file.length - 1] !== "" || fileIndex + tail.length === file.length) {
          return false;
        }
        tailStart--;
        if (!this.#matchOne(file, tail, partial, tailStart, 0)) {
          return false;
        }
        fileTailMatch = tail.length + 1;
      }
    }
    if (!body.length) {
      let sawSome = !!fileTailMatch;
      for (let i2 = fileIndex; i2 < file.length - fileTailMatch; i2++) {
        const f = String(file[i2]);
        sawSome = true;
        if (f === "." || f === ".." || !this.options.dot && f.startsWith(".")) {
          return false;
        }
      }
      return partial || sawSome;
    }
    const bodySegments = [[[], 0]];
    let currentBody = bodySegments[0];
    let nonGsParts = 0;
    const nonGsPartsSums = [0];
    for (const b of body) {
      if (b === GLOBSTAR) {
        nonGsPartsSums.push(nonGsParts);
        currentBody = [[], 0];
        bodySegments.push(currentBody);
      } else {
        currentBody[0].push(b);
        nonGsParts++;
      }
    }
    let i = bodySegments.length - 1;
    const fileLength = file.length - fileTailMatch;
    for (const b of bodySegments) {
      b[1] = fileLength - (nonGsPartsSums[i--] + b[0].length);
    }
    return !!this.#matchGlobStarBodySections(file, bodySegments, fileIndex, 0, partial, 0, !!fileTailMatch);
  }
  // return false for "nope, not matching"
  // return null for "not matching, cannot keep trying"
  #matchGlobStarBodySections(file, bodySegments, fileIndex, bodyIndex, partial, globStarDepth, sawTail) {
    const bs = bodySegments[bodyIndex];
    if (!bs) {
      for (let i = fileIndex; i < file.length; i++) {
        sawTail = true;
        const f = file[i];
        if (f === "." || f === ".." || !this.options.dot && f.startsWith(".")) {
          return false;
        }
      }
      return sawTail;
    }
    const [body, after] = bs;
    while (fileIndex <= after) {
      const m = this.#matchOne(file.slice(0, fileIndex + body.length), body, partial, fileIndex, 0);
      if (m && globStarDepth < this.maxGlobstarRecursion) {
        const sub = this.#matchGlobStarBodySections(file, bodySegments, fileIndex + body.length, bodyIndex + 1, partial, globStarDepth + 1, sawTail);
        if (sub !== false) {
          return sub;
        }
      }
      const f = file[fileIndex];
      if (f === "." || f === ".." || !this.options.dot && f.startsWith(".")) {
        return false;
      }
      fileIndex++;
    }
    return partial || null;
  }
  #matchOne(file, pattern, partial, fileIndex, patternIndex) {
    let fi;
    let pi;
    let pl;
    let fl;
    for (fi = fileIndex, pi = patternIndex, fl = file.length, pl = pattern.length; fi < fl && pi < pl; fi++, pi++) {
      this.debug("matchOne loop");
      let p = pattern[pi];
      let f = file[fi];
      this.debug(pattern, p, f);
      if (p === false || p === GLOBSTAR) {
        return false;
      }
      let hit;
      if (typeof p === "string") {
        hit = f === p;
        this.debug("string match", p, f, hit);
      } else {
        hit = p.test(f);
        this.debug("pattern match", p, f, hit);
      }
      if (!hit)
        return false;
    }
    if (fi === fl && pi === pl) {
      return true;
    } else if (fi === fl) {
      return partial;
    } else if (pi === pl) {
      return fi === fl - 1 && file[fi] === "";
    } else {
      throw new Error("wtf?");
    }
  }
  braceExpand() {
    return braceExpand(this.pattern, this.options);
  }
  parse(pattern) {
    assertValidPattern(pattern);
    const options = this.options;
    if (pattern === "**")
      return GLOBSTAR;
    if (pattern === "")
      return "";
    let m;
    let fastTest = null;
    if (m = pattern.match(starRE)) {
      fastTest = options.dot ? starTestDot : starTest;
    } else if (m = pattern.match(starDotExtRE)) {
      fastTest = (options.nocase ? options.dot ? starDotExtTestNocaseDot : starDotExtTestNocase : options.dot ? starDotExtTestDot : starDotExtTest)(m[1]);
    } else if (m = pattern.match(qmarksRE)) {
      fastTest = (options.nocase ? options.dot ? qmarksTestNocaseDot : qmarksTestNocase : options.dot ? qmarksTestDot : qmarksTest)(m);
    } else if (m = pattern.match(starDotStarRE)) {
      fastTest = options.dot ? starDotStarTestDot : starDotStarTest;
    } else if (m = pattern.match(dotStarRE)) {
      fastTest = dotStarTest;
    }
    const re = AST.fromGlob(pattern, this.options).toMMPattern();
    if (fastTest && typeof re === "object") {
      Reflect.defineProperty(re, "test", { value: fastTest });
    }
    return re;
  }
  makeRe() {
    if (this.regexp || this.regexp === false)
      return this.regexp;
    const set = this.set;
    if (!set.length) {
      this.regexp = false;
      return this.regexp;
    }
    const options = this.options;
    const twoStar = options.noglobstar ? star2 : options.dot ? twoStarDot : twoStarNoDot;
    const flags = new Set(options.nocase ? ["i"] : []);
    let re = set.map((pattern) => {
      const pp = pattern.map((p) => {
        if (p instanceof RegExp) {
          for (const f of p.flags.split(""))
            flags.add(f);
        }
        return typeof p === "string" ? regExpEscape2(p) : p === GLOBSTAR ? GLOBSTAR : p._src;
      });
      pp.forEach((p, i) => {
        const next = pp[i + 1];
        const prev = pp[i - 1];
        if (p !== GLOBSTAR || prev === GLOBSTAR) {
          return;
        }
        if (prev === void 0) {
          if (next !== void 0 && next !== GLOBSTAR) {
            pp[i + 1] = "(?:\\/|" + twoStar + "\\/)?" + next;
          } else {
            pp[i] = twoStar;
          }
        } else if (next === void 0) {
          pp[i - 1] = prev + "(?:\\/|\\/" + twoStar + ")?";
        } else if (next !== GLOBSTAR) {
          pp[i - 1] = prev + "(?:\\/|\\/" + twoStar + "\\/)" + next;
          pp[i + 1] = GLOBSTAR;
        }
      });
      const filtered = pp.filter((p) => p !== GLOBSTAR);
      if (this.partial && filtered.length >= 1) {
        const prefixes = [];
        for (let i = 1; i <= filtered.length; i++) {
          prefixes.push(filtered.slice(0, i).join("/"));
        }
        return "(?:" + prefixes.join("|") + ")";
      }
      return filtered.join("/");
    }).join("|");
    const [open, close] = set.length > 1 ? ["(?:", ")"] : ["", ""];
    re = "^" + open + re + close + "$";
    if (this.partial) {
      re = "^(?:\\/|" + open + re.slice(1, -1) + close + ")$";
    }
    if (this.negate)
      re = "^(?!" + re + ").+$";
    try {
      this.regexp = new RegExp(re, [...flags].join(""));
    } catch {
      this.regexp = false;
    }
    return this.regexp;
  }
  slashSplit(p) {
    if (this.preserveMultipleSlashes) {
      return p.split("/");
    } else if (this.isWindows && /^\/\/[^/]+/.test(p)) {
      return ["", ...p.split(/\/+/)];
    } else {
      return p.split(/\/+/);
    }
  }
  match(f, partial = this.partial) {
    this.debug("match", f, this.pattern);
    if (this.comment) {
      return false;
    }
    if (this.empty) {
      return f === "";
    }
    if (f === "/" && partial) {
      return true;
    }
    const options = this.options;
    if (this.isWindows) {
      f = f.split("\\").join("/");
    }
    const ff = this.slashSplit(f);
    this.debug(this.pattern, "split", ff);
    const set = this.set;
    this.debug(this.pattern, "set", set);
    let filename = ff[ff.length - 1];
    if (!filename) {
      for (let i = ff.length - 2; !filename && i >= 0; i--) {
        filename = ff[i];
      }
    }
    for (const pattern of set) {
      let file = ff;
      if (options.matchBase && pattern.length === 1) {
        file = [filename];
      }
      const hit = this.matchOne(file, pattern, partial);
      if (hit) {
        if (options.flipNegate) {
          return true;
        }
        return !this.negate;
      }
    }
    if (options.flipNegate) {
      return false;
    }
    return this.negate;
  }
  static defaults(def) {
    return minimatch.defaults(def).Minimatch;
  }
};
minimatch.AST = AST;
minimatch.Minimatch = Minimatch;
minimatch.escape = escape;
minimatch.unescape = unescape;

// packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts
var DEFAULT_READ_FILE_CAP = 8;
var DEFAULT_READ_BYTE_CAP = 65536;
var IS_WIN32 = process.platform === "win32";
function isSameOrUnder(prefix, candidate) {
  const a = IS_WIN32 ? prefix.toLowerCase() : prefix;
  const c = IS_WIN32 ? candidate.toLowerCase() : candidate;
  return c === a || c.startsWith(`${a}${path14.sep}`);
}
function normalizeForCompare(projectRoot, p) {
  const abs = path14.resolve(projectRoot, p);
  let cur = abs;
  const tail = [];
  for (; ; ) {
    try {
      return path14.join(fs10.realpathSync(cur), ...tail);
    } catch {
      const parent = path14.dirname(cur);
      if (parent === cur) return abs;
      tail.unshift(path14.basename(cur));
      cur = parent;
    }
  }
}
function isWithinScope(projectRoot, scopeEntries, requestPath) {
  const req = normalizeForCompare(projectRoot, requestPath);
  return scopeEntries.some((entry) => isSameOrUnder(normalizeForCompare(projectRoot, entry), req));
}
function defaultStatSize(absolutePath) {
  try {
    return fs10.statSync(absolutePath).size;
  } catch {
    return 0;
  }
}
function matchedDenyGlob(projectRoot, denyGlobs, rawPath) {
  if (denyGlobs.length === 0) return null;
  const abs = normalizeForCompare(projectRoot, rawPath);
  const rel = path14.relative(projectRoot, abs).replaceAll("\\", "/");
  for (const glob of denyGlobs) {
    if (minimatch(abs, glob) || minimatch(rel, glob)) return glob;
    if (glob.endsWith("/**")) {
      const stripped = glob.slice(0, -3);
      if (stripped !== "" && minimatch(rel, stripped)) return glob;
    }
  }
  return null;
}
function checkReadScopeCall(projectRoot, config, state, tool, rawPath, statSize = defaultStatSize) {
  const denyGlob = matchedDenyGlob(projectRoot, config.denyGlobs, rawPath);
  if (denyGlob !== null) {
    return {
      allowed: false,
      rule: "deny-glob",
      reason: `read_scope: blocked ${tool} of ${rawPath}: the path matches deny glob '${denyGlob}' [rule=deny-glob]`,
      chargedBytes: 0
    };
  }
  if (config.scope !== null && !isWithinScope(projectRoot, config.scope, rawPath)) {
    return {
      allowed: false,
      rule: "scope",
      reason: `read_scope: blocked ${tool} of ${rawPath}: the path resolves outside the allowed read scope (${config.scope.join(", ")}) [rule=scope]`,
      chargedBytes: 0
    };
  }
  if (config.scope !== null && state.allowedCalls >= config.fileCap) {
    return {
      allowed: false,
      rule: "cap-file",
      reason: `read_scope: blocked ${tool} of ${rawPath}: the read file cap is reached (${state.allowedCalls}/${config.fileCap} calls already allowed) [rule=cap-file]`,
      chargedBytes: 0
    };
  }
  let chargedBytes = 0;
  if (tool === "read") {
    chargedBytes = statSize(path14.resolve(projectRoot, rawPath));
    if (state.bytesRead + chargedBytes > config.byteCap) {
      return {
        allowed: false,
        rule: "cap-byte",
        reason: `read_scope: blocked ${tool} of ${rawPath}: the read byte cap would be exceeded (${state.bytesRead}/${config.byteCap} bytes already read, this file is ${chargedBytes}B) [rule=cap-byte]`,
        chargedBytes: 0
      };
    }
  }
  return { allowed: true, chargedBytes };
}
var PARTITION_MODE_LINE_RE = /^\[mw\] mode: partition[ \t]*$/m;
var PARENT_ROOT_LINE_RE = /^Parent root[^:\n]*:[ \t]*(.+)$/m;
function parentRootFromTaskContent(content) {
  if (!PARTITION_MODE_LINE_RE.test(content)) return null;
  const match2 = PARENT_ROOT_LINE_RE.exec(content);
  if (match2 === null) return null;
  const parentRoot = match2[1]?.trim();
  return parentRoot && parentRoot.length > 0 ? parentRoot : null;
}
function applyParentRootUnion(config, parentRoot) {
  if (config === void 0 || parentRoot === null) return config;
  if (config.scope === null || config.scope.length === 0) return config;
  return { ...config, scope: [...config.scope, parentRoot] };
}
function readScopeConfigFromMeta(meta) {
  if (meta.readScope === void 0 && meta.denyGlobs === void 0) return void 0;
  return {
    scope: meta.readScope === void 0 ? null : meta.readScope,
    denyGlobs: meta.denyGlobs ?? [],
    fileCap: meta.readFileCap ?? DEFAULT_READ_FILE_CAP,
    byteCap: meta.readByteCap ?? DEFAULT_READ_BYTE_CAP
  };
}

// packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
var TOOL_ALLOWLISTS = {
  coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
  review: ["read", "find", "grep", "ls"],
  research: ["read", "find", "grep", "ls", "bash"],
  // Autopilot typed dispatches (D-107/VC-023): per-type tool sets must stay
  // EXACTLY equal to the Python-side REGISTRY in
  // packages/multi-workers/autopilot/dispatch.py (entry order included) —
  // the T-17 L0 parity test locks that equality. "fallback" is the internal
  // default bucket, not a dispatchable type.
  "roadmap-writer": ["read", "write", "edit", "find", "grep", "ls"],
  "phase-writer": ["read", "write", "edit", "bash", "find", "grep", "ls"],
  verifier: ["read", "find", "grep", "ls"],
  reviewer: ["read", "find", "grep", "ls"],
  repair: ["read", "write", "edit", "bash", "find", "grep", "ls"],
  // RAG research bucket (mw-rag-integration D-011): renders rag_chat, the only
  // type allowed to call it. PM/`/worker`-dispatched only — the conductor
  // refuses it on the Python side (conductor_dispatchable=False).
  "rag-research": [
    "read",
    "find",
    "grep",
    "ls",
    "rag_search",
    "rag_symbol",
    "rag_graph",
    "rag_impact",
    "rag_sources",
    "rag_feedback",
    "rag_chat"
  ],
  fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"]
};
function isRegisteredType(taskType) {
  return taskType !== "fallback" && taskType in TOOL_ALLOWLISTS;
}
function toolsForType(taskType) {
  return TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? [];
}
var DEFAULT_BUDGET_MS = 60 * 6e4;
var DEFAULT_IDLE_MS = 10 * 6e4;
var CHECKPOINT_ANCHOR_MS = 30 * 6e4;
var CHECKPOINT_REFRESH_MS = 10 * 6e4;
var STEER_MIN_MS = 5 * 6e4;
function resolveBudgetMs(timeoutMin, env) {
  if (timeoutMin !== void 0) return timeoutMin * 6e4;
  const envMs = Number(env);
  if (Number.isFinite(envMs) && envMs > 0) return envMs;
  return DEFAULT_BUDGET_MS;
}
function resolveIdleMs(env) {
  const envMs = Number(env);
  if (Number.isFinite(envMs) && envMs > 0) return envMs;
  return DEFAULT_IDLE_MS;
}
function checkpointAnchorMs(budgetMs) {
  return Math.min(CHECKPOINT_ANCHOR_MS, Math.max(1e3, Math.round(budgetMs / 2)));
}
function steerAtMs(budgetMs) {
  return Math.max(1e3, budgetMs - Math.min(STEER_MIN_MS, Math.round(budgetMs / 4)));
}
var READ_TOOLS = /* @__PURE__ */ new Set(["read", "grep", "find", "ls", "glob"]);
var WRITE_TOOLS = /* @__PURE__ */ new Set(["write", "edit"]);
function computeRisk(s) {
  if (s.writes === 0 && s.elapsedMs >= s.anchorMs) return "high";
  if (s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs || s.repeatTop >= 4) return "mid";
  return "low";
}
function parseTaskMd(taskPath) {
  const content = fs11.readFileSync(taskPath, "utf8");
  const lines = content.split("\n");
  let taskType = "default";
  let phase;
  let timeoutMin;
  let origin;
  const phases = [];
  let currentPhase = null;
  let inPhasePrompt = false;
  let readScope;
  let inReadScopeList = false;
  let denyGlobs;
  let inDenyGlobsList = false;
  let readFileCap;
  let readByteCap;
  let ragChatBudget;
  let ragTimeBudgetS;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("type:")) {
      taskType = trimmed.slice("type:".length).trim();
    }
    if (trimmed.startsWith("phase:")) {
      const v = trimmed.slice("phase:".length).trim();
      if (v) phase = v;
    }
    if (trimmed.startsWith("timeout:")) {
      const v = Number(trimmed.slice("timeout:".length).trim());
      if (Number.isFinite(v) && v > 0) timeoutMin = v;
    }
    if (trimmed.startsWith("origin:")) {
      origin = trimmed.slice("origin:".length).trim();
    }
    if (trimmed === "read_scope:") {
      readScope = [];
      inReadScopeList = true;
    } else if (inReadScopeList && !inPhasePrompt) {
      if (trimmed.startsWith("- ")) {
        const item = trimmed.slice(2).trim();
        if (item) readScope?.push(item);
      } else {
        inReadScopeList = false;
      }
    }
    if (trimmed === "deny_globs:") {
      denyGlobs = [];
      inDenyGlobsList = true;
    } else if (inDenyGlobsList && !inPhasePrompt) {
      if (trimmed.startsWith("- ")) {
        let item = trimmed.slice(2).trim();
        if (item.startsWith('"') && item.endsWith('"') || item.startsWith("'") && item.endsWith("'")) {
          item = item.slice(1, -1);
        }
        if (item) denyGlobs?.push(item);
      } else {
        inDenyGlobsList = false;
      }
    }
    if (trimmed.startsWith("l2_read_file_cap:")) {
      const v = Number(trimmed.slice("l2_read_file_cap:".length).trim());
      if (Number.isFinite(v) && v > 0) readFileCap = v;
    }
    if (trimmed.startsWith("l2_read_byte_cap:")) {
      const v = Number(trimmed.slice("l2_read_byte_cap:".length).trim());
      if (Number.isFinite(v) && v > 0) readByteCap = v;
    }
    if (trimmed.startsWith(RAG_CHAT_BUDGET_HEADER)) {
      const v = Number(trimmed.slice(RAG_CHAT_BUDGET_HEADER.length).trim());
      if (Number.isFinite(v) && v > 0) ragChatBudget = v;
    }
    if (trimmed.startsWith(RAG_TIME_BUDGET_HEADER)) {
      const v = Number(trimmed.slice(RAG_TIME_BUDGET_HEADER.length).trim());
      if (Number.isFinite(v) && v > 0) ragTimeBudgetS = v;
    }
    if (trimmed.startsWith("- name:")) {
      currentPhase = { name: trimmed.slice("- name:".length).trim(), prompt: "" };
      phases.push(currentPhase);
      inPhasePrompt = false;
    } else if (trimmed === "prompt: |" && currentPhase) {
      inPhasePrompt = true;
    } else if (inPhasePrompt && currentPhase) {
      if (trimmed.startsWith("- ") || trimmed.startsWith("name:")) {
        inPhasePrompt = false;
      } else {
        currentPhase.prompt += `${line}
`;
      }
    }
  }
  const agenticdocRoot2 = path15.dirname(path15.dirname(taskPath));
  const taskKey = path15.basename(path15.dirname(taskPath));
  const trueAgenticdocRoot = path15.dirname(path15.dirname(agenticdocRoot2));
  return {
    type: taskType,
    phase,
    phases: phases.length > 0 ? phases : void 0,
    taskKey,
    agenticdocRoot: agenticdocRoot2,
    origin,
    trueAgenticdocRoot,
    timeoutMin,
    readScope,
    denyGlobs,
    readFileCap,
    readByteCap,
    ragChatBudget,
    ragTimeBudgetS
  };
}
function toolTarget2(args) {
  const a = args;
  const raw = typeof a?.path === "string" ? a.path : typeof a?.command === "string" ? a.command : typeof a?.pattern === "string" ? a.pattern : typeof a?.query === "string" ? a.query : "";
  if (!raw) return "";
  return raw.split("\n")[0] ?? "";
}
function toolErrorText(result) {
  const r = result;
  const text = r?.content?.find((c) => typeof c.text === "string")?.text;
  const first = typeof text === "string" ? text.split("\n")[0] ?? "" : "";
  return first || "tool error";
}
function writeWorkerLogLine(line) {
  try {
    fs11.writeSync(1, `${line}
`);
  } catch {
  }
}
function appendStartPidLine(taskKey, agenticdocRoot2) {
  try {
    const dir = path15.resolve(agenticdocRoot2, taskKey);
    fs11.mkdirSync(dir, { recursive: true });
    fs11.appendFileSync(path15.join(dir, "trace.log"), `[START] pid=${process.pid}
`, "utf8");
  } catch {
  }
}
function dispatchRefusal(meta) {
  if (meta.origin !== "conductor") return void 0;
  if (!isRegisteredType(meta.type)) {
    const registered = Object.keys(TOOL_ALLOWLISTS).filter((t) => t !== "fallback").sort().join(", ");
    return `Fail-closed (D-107/VC-023): this task carries origin: conductor but type '${meta.type}' has no tool-allowlist entry \u2014 running it would fall back to the full tool set, which conductor dispatches never get. Registered types: ${registered}.`;
  }
  if (meta.type === "verifier" && (meta.readScope?.length ?? 0) === 0) {
    return "Fail-closed (D-106): verifier dispatches require a non-empty read_scope in task.md \u2014 without one the L2 containment boundary is undefined.";
  }
  return void 0;
}
function appendReadScopeTraceLine(taskKey, agenticdocRoot2, r) {
  try {
    const dir = path15.resolve(agenticdocRoot2, taskKey);
    fs11.mkdirSync(dir, { recursive: true });
    fs11.appendFileSync(
      path15.join(dir, "trace.log"),
      `[READ_SCOPE] ${r.ts} blocked path=${r.path} rule=${r.rule} tool=${r.tool}
`,
      "utf8"
    );
  } catch {
  }
}
function appendReadScopeRejectionsSection(taskKey, agenticdocRoot2, rejections) {
  if (rejections.length === 0) return;
  try {
    const dir = path15.resolve(agenticdocRoot2, taskKey);
    fs11.mkdirSync(dir, { recursive: true });
    const lines = ["## Read Scope Rejections", "", "| tool | rule | path | ts |", "| ---- | ---- | ---- | ---- |"];
    for (const r of rejections) {
      lines.push(`| ${r.tool} | ${r.rule} | ${r.path.replaceAll("|", "\\|")} | ${r.ts} |`);
    }
    fs11.appendFileSync(path15.join(dir, "output.md"), `
${lines.join("\n")}
`, "utf8");
  } catch {
  }
}
function evidencePhase(phase) {
  return phase !== void 0 && phase.length > 0 ? phase : "unknown";
}
var RAG_UNUSED_MARKER = "RAG \u672A\u751F\u6548\uFF1Arequired but unused";
function appendEvidenceOnce(taskDir, line) {
  try {
    const tracePath = path15.join(path15.resolve(taskDir), "trace.log");
    let existing = "";
    try {
      existing = fs11.readFileSync(tracePath, "utf8");
    } catch {
    }
    if (existing.includes(line)) return;
  } catch {
  }
  appendEvidence(taskDir, line);
}
function markOutputRagUnused(taskDir) {
  try {
    const outputPath = path15.join(path15.resolve(taskDir), "output.md");
    if (!fs11.existsSync(outputPath)) return;
    if (fs11.readFileSync(outputPath, "utf8").includes(RAG_UNUSED_MARKER)) return;
    fs11.appendFileSync(outputPath, `
## RAG

${RAG_UNUSED_MARKER}
`, "utf8");
  } catch {
  }
}
function ragServerFor(config, role, phase) {
  return config.roles[role]?.server ?? config.phases[phase]?.server ?? config.defaultServer ?? "";
}
function emitRagRequiredMissing(check) {
  const role = roleForTaskType(check.taskType);
  if (!requiredFor(check.config, role, check.phase)) return null;
  const report = validateResearchDoc(check.keyDir);
  const used = scanCitations(check.outputText).length > 0 || role === "research" && report.citations.length > 0;
  const line = researchDocEvidence(
    { ...report, ok: used },
    role,
    check.phase,
    ragServerFor(check.config, role, check.phase)
  );
  if (line === null) return null;
  appendEvidenceOnce(check.taskDir, line);
  markOutputRagUnused(check.taskDir);
  return line;
}
async function workerModeActivate(pi) {
  const taskPathEnv = process.env.PI_WORKER_TASK;
  if (!taskPathEnv) {
    return;
  }
  const taskPath = path15.resolve(taskPathEnv);
  if (!fs11.existsSync(taskPath)) {
    killTrackedDetachedChildren();
    process.exit(1);
  }
  const meta = parseTaskMd(taskPath);
  const startedAt = Date.now();
  const phaseTotal = meta.phases?.length ?? 0;
  appendStartPidLine(meta.taskKey, meta.agenticdocRoot);
  const refusal = dispatchRefusal(meta);
  if (refusal !== void 0) {
    appendError(meta.taskKey, meta.agenticdocRoot, refusal);
    writeOutput({
      taskKey: meta.taskKey,
      agenticdocRoot: meta.agenticdocRoot,
      exitCode: 1,
      summary: "Task refused at startup (fail-closed).",
      exitReason: refusal
    });
    writeWorkerLogLine(`[worker] refused task=${meta.taskKey} type=${meta.type}: ${refusal}`);
    killTrackedDetachedChildren();
    process.exit(1);
  }
  const readScopeConfig = applyParentRootUnion(
    readScopeConfigFromMeta(meta),
    parentRootFromTaskContent(fs11.readFileSync(taskPath, "utf8"))
  );
  const readScopeState = { allowedCalls: 0, bytesRead: 0 };
  const readScopeRejections = [];
  function writeOutputGuarded(opts) {
    writeOutput(opts);
    appendReadScopeRejectionsSection(meta.taskKey, meta.agenticdocRoot, readScopeRejections);
  }
  appendStart(meta.taskKey, meta.agenticdocRoot, meta.type, phaseTotal);
  pi.on("session_start", (_event, ctx) => {
    const modelId = ctx.model?.id;
    if (modelId) appendModel(meta.taskKey, meta.agenticdocRoot, modelId);
  });
  writeWorkerLogLine(
    `[worker] start task=${meta.taskKey} type=${meta.type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`
  );
  let outputWritten = false;
  process.on("exit", () => {
    try {
      killTrackedDetachedChildren();
    } catch {
    }
    if (outputWritten) return;
    try {
      writeOutputGuarded({
        taskKey: meta.taskKey,
        agenticdocRoot: meta.agenticdocRoot,
        exitCode: 1,
        summary: "(worker exited without writing output)",
        exitReason: "Process exited before output.md was written (crash or unexpected exit)."
      });
    } catch {
    }
  });
  let ragRuntime = null;
  const controlRoot = controlRootFromTaskPath(taskPath);
  const workerTaskDir2 = path15.dirname(taskPath);
  try {
    ragRuntime = registerRagTools(pi, controlRoot, {
      breaker: new Breaker(),
      workerTaskDir: workerTaskDir2,
      role: roleForTaskType(meta.type),
      phase: meta.phase ?? ""
    });
  } catch (err) {
    writeWorkerLogLine(`[worker] rag disabled: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (ragRuntime !== null) {
    await ragRuntime.ready;
    ragRuntime.workerTaskDir = workerTaskDir2;
    ragRuntime.budget = new Budget(
      workerTaskDir2,
      meta.ragChatBudget ?? ragRuntime.config.budgets.chat,
      (meta.ragTimeBudgetS ?? ragRuntime.config.budgets.timeS) * 1e3,
      { taskWallMs: resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS) }
    );
  }
  pi.on("before_agent_start", () => {
    applyRagTools(pi, ragRuntime, meta.type);
  });
  if (readScopeConfig) {
    const projectRoot = process.cwd();
    pi.on("tool_call", (event) => {
      if (event.toolName !== "read" && event.toolName !== "ls" && event.toolName !== "find" && event.toolName !== "grep") {
        return void 0;
      }
      const inputPath = event.input?.path;
      const rawPath = typeof inputPath === "string" && inputPath !== "" ? inputPath : ".";
      const verdict = checkReadScopeCall(projectRoot, readScopeConfig, readScopeState, event.toolName, rawPath);
      if (verdict.allowed) {
        readScopeState.allowedCalls++;
        readScopeState.bytesRead += verdict.chargedBytes;
        return void 0;
      }
      const rejection = {
        tool: event.toolName,
        path: rawPath,
        rule: verdict.rule ?? "scope",
        ts: (/* @__PURE__ */ new Date()).toISOString()
      };
      readScopeRejections.push(rejection);
      appendReadScopeTraceLine(meta.taskKey, meta.agenticdocRoot, rejection);
      return { block: true, reason: verdict.reason };
    });
  }
  let lastActivityAt = startedAt;
  let lastDeltaAt;
  let lastToolAt;
  const touch = () => {
    lastActivityAt = Date.now();
  };
  pi.on("message_update", () => {
    touch();
    lastDeltaAt = Date.now();
  });
  pi.on("message_start", touch);
  pi.on("message_end", touch);
  pi.on("turn_start", touch);
  pi.on("turn_end", touch);
  pi.on("agent_start", touch);
  pi.on("tool_execution_update", touch);
  pi.on("tool_execution_end", touch);
  let toolCallCount = 0;
  let toolErrorCount = 0;
  const toolsUsed = /* @__PURE__ */ new Set();
  let readCount = 0;
  let writeCount = 0;
  const writeTargets = /* @__PURE__ */ new Set();
  const readCounts = /* @__PURE__ */ new Map();
  pi.on("tool_execution_start", (event) => {
    toolCallCount++;
    toolsUsed.add(event.toolName);
    touch();
    lastToolAt = Date.now();
    const target = toolTarget2(event.args);
    if (READ_TOOLS.has(event.toolName)) {
      readCount++;
      if (target) readCounts.set(target, (readCounts.get(target) ?? 0) + 1);
    } else if (WRITE_TOOLS.has(event.toolName)) {
      writeCount++;
      if (target) writeTargets.add(target);
    }
    appendTrace(meta.taskKey, meta.agenticdocRoot, `tool_call ${event.toolName}`);
    appendTool(meta.taskKey, meta.agenticdocRoot, event.toolName, target);
  });
  pi.on("tool_execution_end", (event) => {
    if (!event.isError) return;
    toolErrorCount++;
    appendToolError(meta.taskKey, meta.agenticdocRoot, event.toolName, toolErrorText(event.result));
  });
  let lastAssistantText = "";
  pi.on("agent_end", (event) => {
    touch();
    for (let i = event.messages.length - 1; i >= 0; i--) {
      const msg = event.messages[i];
      if (msg.role === "assistant") {
        const text = msg.content.filter((c) => c.type === "text" && "text" in c).map((c) => c.text).join("\n");
        if (text) lastAssistantText = text;
        break;
      }
    }
  });
  function recordEnd(exitCode) {
    appendEnd(meta.taskKey, meta.agenticdocRoot, {
      exitCode,
      elapsedMs: Date.now() - startedAt,
      toolCalls: toolCallCount,
      phaseDone: meta.phases ? completedPhaseIdx : void 0,
      phaseTotal
    });
    writeWorkerLogLine(
      `[worker] ${exitCode === 0 ? "done" : "failed"} exit=${exitCode} elapsed=${formatHeartbeatAge(
        Date.now() - startedAt
      )} tools=${toolCallCount}${toolErrorCount > 0 ? ` tool_errors=${toolErrorCount}` : ""}${phaseTotal > 0 ? ` phases=${completedPhaseIdx}/${phaseTotal}` : ""}`
    );
  }
  const budgetMs = resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS);
  const idleMs = resolveIdleMs(process.env.PI_WORKER_IDLE_MS);
  const riskAnchorMs = checkpointAnchorMs(budgetMs);
  let taskDone = false;
  let lastCheckpoint;
  let checkpointTimer;
  let steerTimer;
  let idleTimer;
  let wallTimer;
  function clearWatchdogTimers() {
    if (idleTimer) clearInterval(idleTimer);
    if (wallTimer) clearTimeout(wallTimer);
    if (checkpointTimer) clearTimeout(checkpointTimer);
    if (steerTimer) clearTimeout(steerTimer);
  }
  function timeoutExit(kind, detail) {
    taskDone = true;
    clearWatchdogTimers();
    clearInterval(heartbeat);
    appendTimeout(meta.taskKey, meta.agenticdocRoot, kind, detail);
    const ckpt = lastCheckpoint ? ` (checkpoint: risk=${lastCheckpoint.risk} reads=${lastCheckpoint.reads} writes=${lastCheckpoint.writes} phases=${lastCheckpoint.phases})` : "";
    writeOutputGuarded({
      taskKey: meta.taskKey,
      agenticdocRoot: meta.agenticdocRoot,
      exitCode: 1,
      summary: `Worker timed out (${kind}).`,
      exitReason: `${kind} timeout: ${detail}${ckpt}`
    });
    recordEnd(1);
    outputWritten = true;
    killTrackedDetachedChildren();
    process.exit(1);
  }
  function writeCheckpoint() {
    const elapsedMs = Date.now() - startedAt;
    let repeatTop = 0;
    for (const n of readCounts.values()) repeatTop = Math.max(repeatTop, n);
    const phasesStr = phaseTotal > 0 ? `${completedPhaseIdx}/${phaseTotal}` : "-";
    const risk = computeRisk({
      elapsedMs,
      anchorMs: riskAnchorMs,
      writes: writeCount,
      phasesTotal: phaseTotal,
      phasesDone: completedPhaseIdx,
      repeatTop
    });
    appendCheckpoint(meta.taskKey, meta.agenticdocRoot, {
      elapsedMs,
      reads: readCount,
      writes: writeCount,
      phases: phasesStr,
      uniqTargets: writeTargets.size,
      repeatTop,
      risk
    });
    lastCheckpoint = { risk, reads: readCount, writes: writeCount, phases: phasesStr };
    const taskDir = path15.dirname(taskPath);
    pi.sendUserMessage(
      `[mw checkpoint] \u8FD0\u884C ${formatHeartbeatAge(elapsedMs)}\uFF08\u603B\u9884\u7B97 ${formatHeartbeatAge(
        budgetMs
      )}\uFF09\u3002\u8BF7\u7ACB\u5373\u81EA\u8BC4\u6536\u655B\u6027\uFF0C\u628A\u4E00\u884C\u8FFD\u52A0\u5230 ${path15.join(taskDir, "progress.md")}\uFF1ACKPT ${Math.round(
        elapsedMs / 6e4
      )}m converging=yes|no eta\u2248<X>m <\u4E00\u53E5\u8BDD\u7406\u7531>\u3002\u82E5\u4E0D\u6536\u655B\uFF1A\u7ACB\u5373\u6536\u7A84\u8303\u56F4\uFF0C\u4F18\u5148\u4FDD\u8BC1\u5DF2\u5B8C\u6210\u90E8\u5206\u53EF\u4EA4\u4ED8\uFF0C\u4E0D\u8981\u5C55\u5F00\u65B0\u5DE5\u4F5C\u3002`,
      { deliverAs: "followUp" }
    );
  }
  function scheduleCheckpoint(delayMs) {
    checkpointTimer = setTimeout(() => {
      if (taskDone) return;
      writeCheckpoint();
      scheduleCheckpoint(CHECKPOINT_REFRESH_MS);
    }, delayMs);
    checkpointTimer.unref();
  }
  scheduleCheckpoint(riskAnchorMs);
  steerTimer = setTimeout(() => {
    if (taskDone) return;
    pi.sendUserMessage(
      `[mw deadline] \u9884\u7B97\u8FD8\u5269\u7EA6 ${formatHeartbeatAge(
        budgetMs - steerAtMs(budgetMs)
      )}\u3002\u7ACB\u5373\u505C\u6B62\u5F00\u59CB\u65B0\u5DE5\u4F5C\uFF1A\u5B8C\u6210\u5F53\u524D\u6700\u5C0F\u6B65\u9AA4\u540E\u6536\u5C3E\uFF0C\u6700\u7EC8\u56DE\u590D\u4E2D\u5217\u51FA\u5DF2\u5B8C\u6210/\u672A\u5B8C\u6210/\u540E\u7EED\u5EFA\u8BAE\uFF08\u4F1A\u88AB\u5B58\u4E3A output.md \u6458\u8981\uFF09\u3002\u6700\u7EC8\u56DE\u590D\u7B2C\u4E00\u884C\u5FC5\u987B\u662F\u5355\u884C\u7ED3\u8BBA\uFF08\u72B6\u6001 + \u5173\u952E\u4EA7\u51FA/\u5361\u70B9\uFF09\u3002`,
      { deliverAs: "steer" }
    );
  }, steerAtMs(budgetMs));
  steerTimer.unref();
  idleTimer = setInterval(() => {
    if (taskDone) return;
    const idleForMs = Date.now() - lastActivityAt;
    if (idleForMs < idleMs) return;
    const now = Date.now();
    const d = lastDeltaAt === void 0 ? "-" : `${Math.round((now - lastDeltaAt) / 1e3)}`;
    const t = lastToolAt === void 0 ? "-" : `${Math.round((now - lastToolAt) / 1e3)}`;
    timeoutExit(
      "idle",
      `no activity for ${Math.round(idleForMs / 1e3)}s (last delta ${d}s ago, last tool ${t}s ago)`
    );
  }, 3e4);
  idleTimer.unref();
  wallTimer = setTimeout(() => {
    if (taskDone) return;
    const sinceAct = Math.round((Date.now() - lastActivityAt) / 1e3);
    timeoutExit("wall", `budget ${Math.round(budgetMs / 1e3)}s exceeded (last activity ${sinceAct}s ago)`);
  }, budgetMs);
  wallTimer.unref();
  let initialSettled = false;
  let nextPhaseIdx = 0;
  let completedPhaseIdx = 0;
  const phases = meta.phases;
  const heartbeat = setInterval(() => {
    appendHeartbeat(
      meta.taskKey,
      meta.agenticdocRoot,
      phases && phases.length > 0 ? `${completedPhaseIdx}/${phases.length}` : "-"
    );
  }, HEARTBEAT_INTERVAL_MS);
  heartbeat.unref();
  function buildSummary() {
    const base = lastAssistantText || "Task completed.";
    const tools = toolsUsed.size > 0 ? ` Tools used: ${[...toolsUsed].sort().join(", ")} (${toolCallCount} calls).` : "";
    return `${base}${tools}`;
  }
  function finishSuccess() {
    taskDone = true;
    clearWatchdogTimers();
    clearInterval(heartbeat);
    writeOutputGuarded({
      taskKey: meta.taskKey,
      agenticdocRoot: meta.agenticdocRoot,
      exitCode: 0,
      summary: buildSummary(),
      changedFiles: [],
      verificationSteps: "See task output for details.",
      exitReason: `Agent settled after ${toolCallCount} tool call(s).`
    });
    if (ragRuntime !== null) {
      emitRagRequiredMissing({
        config: ragRuntime.config,
        taskType: meta.type,
        phase: evidencePhase(meta.phase),
        outputText: lastAssistantText,
        keyDir: path15.dirname(meta.agenticdocRoot),
        taskDir: path15.dirname(taskPath)
      });
    }
    recordEnd(0);
    outputWritten = true;
  }
  pi.on("agent_settled", () => {
    try {
      if (!initialSettled) {
        initialSettled = true;
        if (phases && phases.length > 0) {
          appendPhase(meta.taskKey, meta.agenticdocRoot, "start", 1, phases.length, phases[0].name);
          pi.sendUserMessage(phases[0].prompt);
          nextPhaseIdx = 1;
          return;
        }
        finishSuccess();
        return;
      }
      if (phases) {
        const phaseIndex = completedPhaseIdx;
        writePhaseFile(
          meta.taskKey,
          meta.agenticdocRoot,
          phaseIndex,
          lastAssistantText || `Phase ${phaseIndex + 1} complete`
        );
        appendGoalCheck(meta.taskKey, meta.agenticdocRoot, phaseIndex + 1, goalMtime(meta.trueAgenticdocRoot));
        completedPhaseIdx++;
        appendPhase(meta.taskKey, meta.agenticdocRoot, "done", phaseIndex + 1, phases.length);
        if (nextPhaseIdx < phases.length) {
          const next = phases[nextPhaseIdx];
          appendPhase(meta.taskKey, meta.agenticdocRoot, "start", nextPhaseIdx + 1, phases.length, next.name);
          pi.sendUserMessage(next.prompt);
          nextPhaseIdx++;
          return;
        }
      }
      finishSuccess();
    } catch (err) {
      taskDone = true;
      clearWatchdogTimers();
      clearInterval(heartbeat);
      appendError(meta.taskKey, meta.agenticdocRoot, String(err));
      writeOutputGuarded({
        taskKey: meta.taskKey,
        agenticdocRoot: meta.agenticdocRoot,
        exitCode: 1,
        summary: "Task failed during output writing.",
        exitReason: String(err)
      });
      recordEnd(1);
      outputWritten = true;
      killTrackedDetachedChildren();
      process.exit(1);
    }
  });
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/cli-bridge.ts
import { spawn as spawn2 } from "node:child_process";

// packages/coding-agent/src/extensions/agent-team-loop/rag/mcp-client.ts
var MCP_PROTOCOL_VERSION = "2025-03-26";
var DEFAULT_MCP_INIT_TIMEOUT_MS = 15e3;
var RagToolError = class extends Error {
  constructor(init) {
    super(init.message);
    this.name = "RagToolError";
    this.kind = init.kind;
    this.server = init.server;
    this.tool = init.tool;
    this.detail = init.detail;
  }
};
var CONNECT_ERROR_CODES = /* @__PURE__ */ new Set([
  "ECONNREFUSED",
  "ECONNRESET",
  "ENOTFOUND",
  "EAI_AGAIN",
  "EHOSTUNREACH",
  "ENETUNREACH",
  "EPIPE",
  "ECONNABORTED",
  "UND_ERR_SOCKET",
  "UND_ERR_CONNECT_TIMEOUT"
]);
var CONNECT_ERROR_MESSAGES = ["socket hang up", "other side closed", "econnrefused", "econnreset", "getaddrinfo"];
var McpSession = class {
  constructor(baseUrl, tokenEnv) {
    this.sessionId = null;
    this.nextRequestId = 0;
    this.baseUrl = baseUrl;
    this.tokenEnv = tokenEnv;
  }
  /** Handshake: capture `Mcp-Session-Id` from the response header. */
  async initialize(timeoutMs = DEFAULT_MCP_INIT_TIMEOUT_MS) {
    const response = await this.send(
      this.buildRequest("initialize", {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: "mw-rag", version: "1.0.0" }
      }),
      timeoutMs,
      void 0,
      "initialize"
    );
    this.parseEnvelope(response, "initialize");
    if (response.sessionId === null || response.sessionId.length === 0) {
      throw this.buildError("protocol", "initialize", "initialize response is missing the Mcp-Session-Id header", {
        status: response.status
      });
    }
    this.sessionId = response.sessionId;
  }
  /** `tools/call`; returns the tool payload (MCP `content[0].text` JSON is unwrapped). */
  async callTool(name, args, opts) {
    const response = await this.send(
      this.buildRequest("tools/call", { name, arguments: args ?? {} }),
      opts.timeoutMs,
      opts.signal,
      name
    );
    const result = this.parseEnvelope(response, name);
    return this.unwrapToolResult(result, name);
  }
  buildRequest(method, params) {
    this.nextRequestId += 1;
    return { jsonrpc: "2.0", id: this.nextRequestId, method, params };
  }
  async send(request, timeoutMs, externalSignal, tool) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const onExternalAbort = () => controller.abort();
    if (externalSignal !== void 0) {
      if (externalSignal.aborted) controller.abort();
      else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
    try {
      const headers = {
        "Content-Type": "application/json",
        Accept: "application/json"
      };
      const token = this.tokenValue();
      if (token !== null) headers["X-MCP-Token"] = token;
      if (this.sessionId !== null) headers["Mcp-Session-Id"] = this.sessionId;
      const response = await fetch(this.baseUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(request),
        signal: controller.signal
      });
      const text = await response.text();
      return { status: response.status, text, sessionId: response.headers.get("mcp-session-id") };
    } catch (error) {
      if (controller.signal.aborted) {
        throw this.buildError("timeout", tool, `request timed out after ${timeoutMs}ms`, {
          method: request.method
        });
      }
      throw this.buildError(classifyFetchFailure(error), tool, describeFetchFailure(error), {
        method: request.method
      });
    } finally {
      clearTimeout(timer);
      if (externalSignal !== void 0) externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
  parseEnvelope(response, tool) {
    if (response.status === 401 || response.status === 403) {
      throw this.buildError("protocol", tool, `authentication rejected (HTTP ${response.status})`, {
        status: response.status,
        body: this.redact(snippet(response.text))
      });
    }
    if (response.status < 200 || response.status >= 300) {
      throw this.buildError("protocol", tool, `unexpected HTTP status ${response.status}`, {
        status: response.status,
        body: this.redact(snippet(response.text))
      });
    }
    let parsed;
    try {
      parsed = JSON.parse(response.text);
    } catch {
      throw this.buildError("protocol", tool, "response is not valid JSON", {
        body: this.redact(snippet(response.text))
      });
    }
    if (!isRecord(parsed)) {
      throw this.buildError("protocol", tool, "JSON-RPC response is not an object", {
        body: this.redact(snippet(response.text))
      });
    }
    const error = parsed.error;
    if (isRecord(error)) {
      const detail = this.redactDetail(error);
      throw this.buildError(
        "tool",
        tool,
        stringField(error, "message") ?? "server returned a JSON-RPC error",
        detail
      );
    }
    if (!("result" in parsed)) {
      throw this.buildError("protocol", tool, "JSON-RPC response has neither result nor error", {
        body: this.redact(snippet(response.text))
      });
    }
    return parsed.result;
  }
  tokenValue() {
    if (this.tokenEnv === null) return null;
    const value = process.env[this.tokenEnv];
    return value !== void 0 && value.length > 0 ? value : null;
  }
  redact(text) {
    const token = this.tokenValue();
    if (token === null) return text;
    return text.split(token).join("<redacted>");
  }
  redactDetail(detail) {
    if (detail === void 0) return void 0;
    const token = this.tokenValue();
    if (token === null) return detail;
    try {
      return JSON.parse(this.redact(JSON.stringify(detail)));
    } catch {
      return "<redacted>";
    }
  }
  unwrapToolResult(result, tool) {
    if (!isRecord(result)) return result;
    if (result.isError === true) {
      throw this.buildError("tool", tool, contentText(result) ?? "tool returned isError=true", result);
    }
    const text = contentText(result);
    if (text === null) return result;
    try {
      return JSON.parse(text);
    } catch {
      return result;
    }
  }
  buildError(kind, tool, message, detail) {
    return new RagToolError({
      kind,
      server: this.baseUrl,
      tool,
      message: this.redact(message),
      detail: this.redactDetail(detail)
    });
  }
};
function contentText(result) {
  const content = result.content;
  if (!Array.isArray(content)) return null;
  for (const entry of content) {
    if (isRecord(entry) && entry.type === "text" && typeof entry.text === "string") return entry.text;
  }
  return null;
}
function classifyFetchFailure(error) {
  const codes = collectErrorCodes(error);
  for (const code of codes) {
    if (CONNECT_ERROR_CODES.has(code)) return "connect";
  }
  const messages = collectErrorMessages(error).join(" ").toLowerCase();
  for (const fragment of CONNECT_ERROR_MESSAGES) {
    if (messages.includes(fragment)) return "connect";
  }
  return "connect";
}
function describeFetchFailure(error) {
  const messages = collectErrorMessages(error);
  if (messages.length > 0) return `request failed: ${messages.join("; ")}`;
  return "request failed before an HTTP response was received";
}
function collectErrorCodes(error) {
  const codes = [];
  visitErrors(error, (record) => {
    if (typeof record.code === "string") codes.push(record.code);
  });
  return codes;
}
function collectErrorMessages(error) {
  const messages = [];
  visitErrors(error, (record) => {
    if (typeof record.message === "string" && record.message.length > 0) messages.push(record.message);
  });
  return messages;
}
function visitErrors(value, visit) {
  const seen = /* @__PURE__ */ new Set();
  const walk = (current, depth) => {
    if (depth > 5 || !isRecord(current) || seen.has(current)) return;
    seen.add(current);
    visit(current);
    if (Array.isArray(current.errors)) for (const entry of current.errors) walk(entry, depth + 1);
    walk(current.cause, depth + 1);
  };
  walk(value, 0);
}
function stringField(record, key) {
  const value = record[key];
  return typeof value === "string" ? value : null;
}
function snippet(text) {
  return text.length > 300 ? text.slice(0, 300) : text;
}
function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/cli-bridge.ts
var SECRET_ENV_KEY_RE = /(token|secret|password|passwd|api[_-]?key|credential)/i;
function resolveRagPython(env = process.env) {
  const override = env.MW_RAG_PYTHON?.trim();
  if (override !== void 0 && override.length > 0) return override;
  return process.platform === "win32" ? "python" : "python3";
}
async function callCli(cliEntry, name, args, opts) {
  const argv = [cliEntry.cliEntry, name];
  for (const [key, value] of Object.entries(args)) {
    if (value === void 0 || value === null) continue;
    argv.push("--arg", `${key}=${serializeArg(value)}`);
  }
  const interpreter = resolveRagPython(opts.env);
  const server = cliEntry.cliEntry;
  if (opts.signal.aborted) throw cliError("timeout", server, name, "call cancelled before spawn");
  return await new Promise((resolve15, reject) => {
    const child = spawn2(interpreter, argv, {
      cwd: cliEntry.dir,
      env: opts.env,
      shell: false,
      windowsHide: true
    });
    const stdoutChunks = [];
    const stderrChunks = [];
    let timedOut = false;
    let settled = false;
    const timeoutMs = cliEntry.timeoutMs;
    const timer = Number.isFinite(timeoutMs) && timeoutMs > 0 ? setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs) : void 0;
    const onAbort = () => {
      child.kill();
    };
    opts.signal.addEventListener("abort", onAbort, { once: true });
    const cleanup = () => {
      if (timer !== void 0) clearTimeout(timer);
      opts.signal.removeEventListener("abort", onAbort);
    };
    child.stdout.on("data", (chunk) => stdoutChunks.push(chunk));
    child.stderr.on("data", (chunk) => stderrChunks.push(chunk));
    child.stdin.end();
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(
        cliError("connect", server, name, `failed to start ${interpreter}: ${error.message}`, {
          code: error.code
        })
      );
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      cleanup();
      const rawStderr = Buffer.concat(stderrChunks).toString("utf8");
      const stderr = redactEnvSecrets(rawStderr, opts.env);
      const detail = {
        exitCode: code,
        stderr: stderr.length > 0 ? truncate(stderr) : void 0
      };
      if (timedOut || code === null && opts.signal.aborted) {
        reject(cliError("timeout", server, name, `cli call timed out after ${timeoutMs}ms`, detail));
        return;
      }
      if (code === 0) {
        const text = Buffer.concat(stdoutChunks).toString("utf8").trim();
        if (text.length === 0) {
          reject(cliError("protocol", server, name, "cli produced no stdout JSON", detail));
          return;
        }
        try {
          resolve15(JSON.parse(text));
        } catch {
          reject(cliError("protocol", server, name, "cli stdout is not valid JSON", detail));
        }
        return;
      }
      if (code === 2) {
        reject(cliError("connect", server, name, "cli reported a connection or usage failure", detail));
        return;
      }
      if (code === 3) {
        reject(cliError("tool", server, name, "cli reported a tool-level error", detail));
        return;
      }
      reject(cliError("protocol", server, name, `cli exited with unexpected code ${String(code)}`, detail));
    });
  });
}
function cliError(kind, server, tool, message, detail) {
  return new RagToolError({ kind, server, tool, message, detail });
}
function serializeArg(value) {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return String(value);
  return JSON.stringify(value);
}
function redactEnvSecrets(text, env) {
  if (text.length === 0) return text;
  let redacted = text;
  for (const [key, value] of Object.entries(env)) {
    if (value === void 0 || value.length < 4) continue;
    if (!SECRET_ENV_KEY_RE.test(key)) continue;
    redacted = redacted.split(value).join("<redacted>");
  }
  return redacted;
}
function truncate(text) {
  return text.length > 1e3 ? text.slice(0, 1e3) : text;
}

// packages/coding-agent/src/extensions/agent-team-loop/rag/guidelines.ts
var RAG_PROMPT_GUIDELINES = [
  "Prefer rag_symbol / rag_graph for precise symbol and relationship lookups; use rag_search only when the symbol is unknown.",
  "Quote citations exactly as returned by the tools (server:source:file_path:line); never assemble a citation by hand.",
  "A RAG result counts as used only after it is written to rag/*.md with its citation and local verification state."
];

// packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts
var RAG_PROBE_TIMEOUT_MS = 5e3;
var RAG_CHAT_BUDGET_HEADER = "rag_chat_budget:";
var RAG_TIME_BUDGET_HEADER = "rag_time_budget_s:";
var RAG_BASE_TOOL_NAMES = [
  "rag_search",
  "rag_symbol",
  "rag_graph",
  "rag_impact",
  "rag_sources",
  "rag_feedback"
];
var RAG_CHAT_TOOL_NAME = "rag_chat";
var RAG_CHAT_TIMEOUT_MS = 6e5;
function ragCallTimeoutMs(logicalTool, config) {
  return logicalTool === RAG_CHAT_TOOL_NAME ? Math.max(config.timeoutMs, RAG_CHAT_TIMEOUT_MS) : config.timeoutMs;
}
function failResult(error) {
  return { content: [{ type: "text", text: JSON.stringify(error) }], details: error };
}
function okResult(envelope) {
  return { content: [{ type: "text", text: JSON.stringify(envelope) }], details: envelope };
}
function serverEnum(enabled) {
  const literals = enabled.map((name) => typebox_exports.Literal(name));
  if (literals.length === 1) {
    const only = literals[0];
    if (only !== void 0) return only;
  }
  return typebox_exports.Union(literals);
}
function registerRagTools(pi, controlRoot, hooks = {}) {
  const config = loadRagConfig(controlRoot);
  if (config.enabled.length === 0) return null;
  const runtime = {
    config,
    controlRoot,
    workerTaskDir: hooks.workerTaskDir ?? null,
    reachable: /* @__PURE__ */ new Map(),
    sessions: /* @__PURE__ */ new Map(),
    breaker: hooks.breaker ?? null,
    budget: hooks.budget ?? null,
    ready: Promise.resolve(),
    chatRegistered: false,
    role: hooks.role ?? "",
    phase: hooks.phase ?? ""
  };
  runtime.ready = probeAndRegister(pi, runtime);
  return runtime;
}
async function probeAndRegister(pi, runtime) {
  await Promise.all(
    runtime.config.enabled.map(async (server) => {
      const entry = runtime.config.servers[server];
      if (entry === void 0 || entry.mcp === null) {
        runtime.reachable.set(server, true);
        return;
      }
      try {
        const session = new McpSession(entry.mcp.url, entry.mcp.tokenEnv);
        await session.initialize(RAG_PROBE_TIMEOUT_MS);
        runtime.sessions.set(server, session);
        runtime.reachable.set(server, true);
      } catch {
        runtime.reachable.set(server, false);
      }
    })
  );
  registerBaseTools(pi, runtime);
}
function withReachability(runtime, description) {
  const anyUnreachable = runtime.config.enabled.some((server) => runtime.reachable.get(server) === false);
  return anyUnreachable ? `${description} [unreachable at session start]` : description;
}
function registerBaseTools(pi, runtime) {
  const enumSchema = serverEnum(runtime.config.enabled);
  pi.registerTool({
    name: "rag_search",
    label: "RAG search",
    description: withReachability(
      runtime,
      "Semantic/keyword search across the configured RAG sources. Returns normalized items with citation and local_path verification state."
    ),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      query: typebox_exports.String({ description: "Natural-language or keyword query." }),
      server: typebox_exports.Optional(enumSchema),
      source: typebox_exports.Optional(typebox_exports.String({ description: "Restrict the search to one source (e.g. docs, code)." })),
      collection: typebox_exports.Optional(typebox_exports.String({ description: "Restrict the search to one collection." })),
      top_k: typebox_exports.Optional(typebox_exports.Number({ description: "Maximum number of hits to return." })),
      multi_rounds: typebox_exports.Optional(typebox_exports.Boolean({ description: "Allow the server to run multiple recall rounds." })),
      auto_rewrite: typebox_exports.Optional(typebox_exports.Boolean({ description: "Allow query rewriting before recall." }))
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_search", params, signal, wrapOnUpdate(onUpdate))
  });
  pi.registerTool({
    name: "rag_symbol",
    label: "RAG symbol",
    description: withReachability(
      runtime,
      "Locate a symbol by name and return its definition plus caller/callee summary with citations."
    ),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      symbol_name: typebox_exports.String({ description: "Symbol name to resolve (function, class, type)." }),
      server: typebox_exports.Optional(enumSchema),
      source: typebox_exports.Optional(typebox_exports.String({ description: "Restrict the lookup to one source." }))
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_symbol", params, signal, wrapOnUpdate(onUpdate))
  });
  pi.registerTool({
    name: "rag_graph",
    label: "RAG graph",
    description: withReachability(
      runtime,
      "Walk the static knowledge graph: callers, callees, inheritance or a subgraph around a symbol."
    ),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      operation: typebox_exports.Union([
        typebox_exports.Literal("callers"),
        typebox_exports.Literal("callees"),
        typebox_exports.Literal("inheritance"),
        typebox_exports.Literal("subgraph")
      ]),
      symbol_name: typebox_exports.String({ description: "Symbol the graph walk is anchored on." }),
      server: typebox_exports.Optional(enumSchema),
      source: typebox_exports.Optional(typebox_exports.String({ description: "Restrict the walk to one source." })),
      depth: typebox_exports.Optional(typebox_exports.Number({ minimum: 1, maximum: 10, description: "Traversal depth (1..10)." })),
      limit: typebox_exports.Optional(typebox_exports.Number({ description: "Maximum number of edges to return." }))
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_graph", params, signal, wrapOnUpdate(onUpdate))
  });
  pi.registerTool({
    name: "rag_impact",
    label: "RAG impact",
    description: withReachability(
      runtime,
      "Estimate the change impact of a symbol: total callers, affected files and callers grouped by hop."
    ),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      symbol: typebox_exports.String({ description: "Symbol whose change impact is measured." }),
      server: typebox_exports.Optional(enumSchema),
      source: typebox_exports.Optional(typebox_exports.String({ description: "Restrict the analysis to one source." })),
      depth: typebox_exports.Optional(typebox_exports.Number({ minimum: 1, maximum: 10, description: "Traversal depth (1..10)." }))
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_impact", params, signal, wrapOnUpdate(onUpdate))
  });
  pi.registerTool({
    name: "rag_sources",
    label: "RAG sources",
    description: withReachability(runtime, "List the RAG sources and their collections for one server."),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      server: typebox_exports.Optional(enumSchema)
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_sources", params, signal, wrapOnUpdate(onUpdate))
  });
  pi.registerTool({
    name: "rag_feedback",
    label: "RAG feedback",
    description: withReachability(
      runtime,
      "Report a mismatch between an expected and an actual RAG result back to the server (write operation, never auto-retried)."
    ),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      title: typebox_exports.String({ description: "Short feedback title." }),
      tool: typebox_exports.String({ description: "Tool the feedback is about." }),
      expected: typebox_exports.String({ description: "What the caller expected." }),
      actual: typebox_exports.String({ description: "What the tool actually returned." }),
      scenario: typebox_exports.Optional(typebox_exports.String({ description: "Optional scenario/context." })),
      detail: typebox_exports.Optional(typebox_exports.String({ description: "Optional free-form detail." })),
      server: typebox_exports.Optional(enumSchema)
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, "rag_feedback", params, signal, wrapOnUpdate(onUpdate))
  });
}
function ensureRagChatTool(pi, runtime) {
  if (runtime.chatRegistered) return;
  runtime.chatRegistered = true;
  const enumSchema = serverEnum(runtime.config.enabled);
  pi.registerTool({
    name: RAG_CHAT_TOOL_NAME,
    label: "RAG chat",
    description: withReachability(
      runtime,
      "Ask the RAG server to synthesize an answer from its sources (lead only; expensive, never auto-retried)."
    ),
    promptGuidelines: RAG_PROMPT_GUIDELINES,
    parameters: typebox_exports.Object({
      query: typebox_exports.String({ description: "Question for the RAG server to answer from its sources." }),
      server: typebox_exports.Optional(enumSchema),
      source: typebox_exports.Optional(typebox_exports.String({ description: "Restrict the answer to one source." })),
      top_k: typebox_exports.Optional(typebox_exports.Number({ description: "Maximum number of supporting hits." })),
      max_recall_rounds: typebox_exports.Optional(typebox_exports.Number({ description: "Maximum recall rounds." }))
    }),
    execute: async (_toolCallId, params, signal, onUpdate) => await callRag(runtime, RAG_CHAT_TOOL_NAME, params, signal, wrapOnUpdate(onUpdate))
  });
}
function ragToolNamesForType(rt, type) {
  const names = [...RAG_BASE_TOOL_NAMES];
  if (rt.config.enabled.length > 0 && type === "rag-research") names.push(RAG_CHAT_TOOL_NAME);
  return names;
}
function applyRagTools(pi, rt, type) {
  if (rt === null) {
    pi.setActiveTools(toolsForType(type));
    return;
  }
  if (type === "rag-research") ensureRagChatTool(pi, rt);
  pi.setActiveTools([.../* @__PURE__ */ new Set([...toolsForType(type), ...ragToolNamesForType(rt, type)])]);
}
function validateRagEnabled(projectDir) {
  try {
    loadRagConfig(projectDir);
    return { ok: true };
  } catch (error) {
    if (error instanceof RagConfigError) {
      return { ok: false, message: `RAG config rejected dispatch (${error.kind}): ${error.message}` };
    }
    throw error;
  }
}
function wrapOnUpdate(onUpdate) {
  if (onUpdate === void 0) return void 0;
  return (message) => onUpdate({ content: [{ type: "text", text: message }], details: void 0 });
}
async function callRag(runtime, tool, params, signal, onUpdate) {
  const tokenEnvNames = ragTokenEnvNames(runtime.config);
  const defaults2 = resolveDefaults(runtime.config, runtime.role, runtime.phase);
  const requested = typeof params.server === "string" && params.server.length > 0 ? params.server : void 0;
  const server = requested ?? defaults2.server;
  if (server === null) {
    return failResult({
      kind: "tool",
      server: "",
      tool,
      message: `no RAG server selected for ${tool} and no default_server configured`
    });
  }
  const entry = runtime.config.servers[server];
  if (entry === void 0) {
    return failResult({ kind: "tool", server, tool, message: `unknown rag server '${server}'` });
  }
  const taskDir = runtime.workerTaskDir;
  const evidence = (line) => {
    if (taskDir !== null) appendEvidence(taskDir, redactSecrets(line, tokenEnvNames));
  };
  if (runtime.breaker?.isOpen(server)) {
    evidence(ragUnavailableLine({ server, tool, kind: "circuit", ms: 0 }));
    return failResult({ kind: "circuit", server, tool, message: `circuit open for rag server '${server}'` });
  }
  const capability = capabilityError(server, tool, entry.capabilities);
  if (capability !== null) return failResult(capability);
  const isChat = tool === RAG_CHAT_TOOL_NAME;
  const budget = runtime.budget;
  if (budget !== null) {
    const cumulative = budget.checkCumulative();
    if (!cumulative.ok) {
      const state = budget.state();
      evidence(
        ragBudgetExceededLine({
          server,
          tool,
          reason: "cumulative",
          used: state.timeUsedMs,
          budget: state.timeBudgetMs
        })
      );
      return failResult({ kind: "budget", server, tool, message: cumulative.message });
    }
    if (isChat) {
      const wall = budget.checkWall(Date.now());
      if (!wall.ok) {
        evidence(
          ragBudgetExceededLine({
            server,
            tool,
            reason: "wall",
            used: Math.max(0, Date.now() - budget.startedAt),
            budget: budget.taskWallMs ?? 0
          })
        );
        return failResult({ kind: "budget", server, tool, message: wall.message });
      }
      const reserved = budget.reserveChat();
      if (!reserved.ok) {
        const state = budget.state();
        evidence(
          ragBudgetExceededLine({
            server,
            tool,
            reason: "count",
            used: state.chatUsed,
            budget: state.chatBudget
          })
        );
        return failResult({ kind: "budget", server, tool, message: reserved.message });
      }
    }
  }
  const args = {};
  for (const [key, value] of Object.entries(params)) {
    if (key !== "server" && value !== void 0) args[key] = value;
  }
  const explicitSource = typeof params.source === "string" && params.source.length > 0 ? params.source : void 0;
  const source = explicitSource ?? defaults2.source;
  if (explicitSource === void 0 && source !== null) args.source = source;
  if (tool === "rag_search" && args.multi_rounds === void 0 && args.auto_rewrite === void 0) {
    const explicitRewrite = runtime.config.roles[runtime.role]?.rewrite ?? runtime.config.phases[runtime.phase]?.rewrite;
    if (rewriteDefaults(runtime.role, runtime.phase, entry.capabilities.rewrite, explicitRewrite)) {
      args.multi_rounds = true;
    }
  }
  const startedAt = Date.now();
  try {
    const calls = ragToolCalls(tool, args);
    const outcomes = await withHeartbeat(RAG_HEARTBEAT_INTERVAL_MS, onUpdate, async () => {
      const legs = [];
      for (const call of calls) {
        legs.push(await transport(runtime, server, entry, tool, call.name, call.args, signal, onUpdate));
      }
      return legs;
    });
    const roots = loadPathRoots(resolvePathRootsFile(runtime.controlRoot, entry));
    const envelope = normalizeResults(
      server,
      tool,
      source,
      mergeToolResponses(
        tool,
        outcomes.map((leg) => leg.response)
      ),
      roots
    );
    envelope.mcp_tool = calls.map((call) => call.name).join("+");
    const elapsed = Date.now() - startedAt;
    runtime.budget?.accumulate(elapsed);
    if (isChat) runtime.budget?.settleChat(true, null);
    runtime.breaker?.noteSuccess(server);
    if (outcomes.some((leg) => leg.fallback)) {
      evidence(ragFallbackLine({ server, tool, reason: "connect" }));
    }
    if (envelope.meta.rewrite_degraded === true) evidence(ragRewriteDegradedLine({ server, tool }));
    evidence(
      ragCallLine({
        server,
        tool,
        via: outcomes.some((leg) => leg.via === "cli") ? "cli" : "mcp",
        ms: elapsed,
        results: evidenceResults(envelope),
        mcpTool: envelope.mcp_tool ?? null
      })
    );
    return okResult(envelope);
  } catch (error) {
    const elapsed = Date.now() - startedAt;
    const tagged = retag(error, server, tool);
    runtime.budget?.accumulate(elapsed);
    runtime.breaker?.noteFailure(server, tagged.kind);
    if (isChat) runtime.budget?.settleChat(false, tagged.kind);
    evidence(ragUnavailableLine({ server, tool, kind: tagged.kind, ms: elapsed }));
    return failResult(redactToolError(tagged, tokenEnvNames));
  }
}
function ragTokenEnvNames(config) {
  const names = /* @__PURE__ */ new Set();
  for (const entry of Object.values(config.servers)) {
    const name = entry.mcp?.tokenEnv;
    if (name !== void 0 && name !== null && name.length > 0) names.add(name);
  }
  return [...names];
}
function evidenceResults(envelope) {
  if (envelope.tool === "rag_feedback") return 0;
  const affected = envelope.meta.affected_files;
  if (envelope.tool === "rag_impact" && Array.isArray(affected)) return affected.length;
  return envelope.items.length;
}
function redactToolError(error, tokenEnvNames) {
  const message = redactSecrets(error.message, tokenEnvNames);
  return { ...error, message, detail: redactDetail(error.detail, tokenEnvNames) };
}
function redactDetail(detail, tokenEnvNames) {
  if (detail === void 0) return void 0;
  try {
    return JSON.parse(redactSecrets(JSON.stringify(detail), tokenEnvNames));
  } catch {
    return redactSecrets(String(detail), tokenEnvNames);
  }
}
function resolvePathRootsFile(controlRoot, entry) {
  if (entry.pathRootsFile === null || entry.pathRootsFile.length === 0) return null;
  return path16.resolve(controlRoot, entry.pathRootsFile);
}
async function transport(runtime, server, entry, logicalTool, mcpTool, args, signal, onUpdate) {
  const canMcp = (entry.transport === "mcp" || entry.transport === "both") && entry.mcp !== null;
  const canCli = (entry.transport === "skill" || entry.transport === "both") && entry.skill !== null;
  const readOnly = logicalTool !== "rag_feedback" && logicalTool !== RAG_CHAT_TOOL_NAME;
  if (canMcp) {
    try {
      return {
        response: await mcpCall(runtime, server, entry, mcpTool, args, signal, onUpdate, logicalTool),
        via: "mcp",
        fallback: false
      };
    } catch (error) {
      const kind = error instanceof RagToolError ? error.kind : "protocol";
      if (!(canCli && kind === "connect" && readOnly)) throw error;
      return {
        response: await cliCall(runtime, entry, logicalTool, args, signal, onUpdate),
        via: "cli",
        fallback: true
      };
    }
  }
  if (canCli) {
    return {
      response: await cliCall(runtime, entry, logicalTool, args, signal, onUpdate),
      via: "cli",
      fallback: false
    };
  }
  throw new RagToolError({
    kind: "tool",
    server,
    tool: logicalTool,
    message: `rag server '${server}' has no usable transport`
  });
}
async function mcpCall(runtime, server, entry, tool, args, signal, onUpdate, logicalTool) {
  const mcp = entry.mcp;
  if (mcp === null) throw new RagToolError({ kind: "tool", server, tool, message: "mcp is not configured" });
  let session = runtime.sessions.get(server);
  if (session === void 0) {
    session = new McpSession(mcp.url, mcp.tokenEnv);
    await session.initialize(mcp.timeoutMs);
    runtime.sessions.set(server, session);
  }
  return await session.callTool(tool, args, {
    // rag_chat gets the 600s floor (T-09); every other logical tool keeps
    // the configured mcp.timeout_ms. `tool` here is the wire name, so the
    // decision keys off the logical name the agent invoked.
    timeoutMs: ragCallTimeoutMs(logicalTool, mcp),
    signal: signal ?? new AbortController().signal,
    onUpdate
  });
}
function resolveCliDir(controlRoot, dir) {
  return dir === null ? controlRoot : path16.resolve(controlRoot, dir);
}
async function cliCall(runtime, entry, tool, args, signal, onUpdate) {
  const skill = entry.skill;
  if (skill === null) throw new Error(`rag server has no skill block for tool ${tool}`);
  const dir = resolveCliDir(runtime.controlRoot, skill.dir);
  return await callCli({ dir, cliEntry: skill.cliEntry, timeoutMs: skill.timeoutMs }, tool, args, {
    signal: signal ?? new AbortController().signal,
    env: process.env,
    onUpdate
  });
}
function retag(error, server, tool) {
  if (error instanceof RagToolError) {
    return { kind: error.kind, server, tool, message: error.message, detail: error.detail };
  }
  return {
    kind: "tool",
    server,
    tool,
    message: error instanceof Error ? error.message : String(error)
  };
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts
import { spawnSync as spawnSync3 } from "node:child_process";
import * as fs13 from "node:fs";
import * as path18 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts
import { spawn as spawn3, spawnSync as spawnSync2 } from "node:child_process";
import * as fs12 from "node:fs";
import * as os2 from "node:os";
import * as path17 from "node:path";
import { fileURLToPath as fileURLToPath3 } from "node:url";
var PYTHON_EXE = process.platform === "win32" ? "python" : "python3";
function globalExtDir() {
  const envDir = process.env.PI_CODING_AGENT_DIR;
  const base = envDir ? envDir : path17.join(os2.homedir(), ".pi", "agent");
  return path17.join(base, "extensions");
}
function findMwPy() {
  const envPath = process.env.MW_PY;
  if (envPath && fs12.existsSync(envPath)) return envPath;
  try {
    const rec = path17.join(globalExtDir(), ".mw-py-path");
    if (fs12.existsSync(rec)) {
      const recorded = fs12.readFileSync(rec, "utf8").trim();
      if (recorded && fs12.existsSync(recorded)) return recorded;
    }
  } catch {
  }
  try {
    const here = path17.dirname(fileURLToPath3(import.meta.url));
    const candidate = path17.resolve(here, "../../../../../multi-workers/mw.py");
    if (fs12.existsSync(candidate)) return candidate;
  } catch {
  }
  return null;
}
function buildMw() {
  const mwPy = findMwPy();
  if (!mwPy) return { ok: false, error: "Could not find mw.py \u2014 set MW_PY env var." };
  const result = spawnSync2(PYTHON_EXE, [mwPy, "build", "--install"], {
    encoding: "utf8",
    timeout: 12e4
  });
  if (result.error) {
    return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
  }
  if (result.status !== 0) {
    const stderr = result.stderr?.trim();
    return { ok: false, error: stderr || `mw build exited with code ${result.status}` };
  }
  return { ok: true, output: (result.stdout || "").trim() };
}
function pidFilePath(projectDir) {
  return path17.join(projectDir, ".mw", "mw.pid");
}
function getMwStatus(projectDir) {
  const pidPath = pidFilePath(projectDir);
  if (!fs12.existsSync(pidPath)) return { running: false, pid: null };
  const raw = fs12.readFileSync(pidPath, "utf8").trim();
  const pid = Number.parseInt(raw, 10);
  if (Number.isNaN(pid)) return { running: false, pid: null };
  try {
    process.kill(pid, 0);
    return { running: true, pid };
  } catch {
    return { running: false, pid: null };
  }
}
function initMw(projectDir) {
  const mwPy = findMwPy();
  if (!mwPy) return { ok: false, error: "Could not find mw.py \u2014 set MW_PY env var." };
  const result = spawnSync2(PYTHON_EXE, [mwPy, "init", `--project=${projectDir}`], {
    encoding: "utf8",
    timeout: 3e4
  });
  if (result.error) {
    return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
  }
  if (result.status !== 0) {
    const stderr = result.stderr?.trim();
    return { ok: false, error: stderr || `mw init exited with code ${result.status}` };
  }
  return { ok: true };
}
function startMw(projectDir) {
  const mwPy = findMwPy();
  if (!mwPy) return false;
  const child = spawn3(PYTHON_EXE, [mwPy, "start", `--project=${projectDir}`], {
    detached: true,
    stdio: "ignore",
    windowsHide: true
  });
  child.unref();
  return true;
}
async function waitForMwStart(projectDir, timeoutMs = 8e3, stableMs = 3e3) {
  return waitForStart(() => getMwStatus(projectDir), timeoutMs, stableMs);
}
async function waitForStart(statusFn, timeoutMs, stableMs, pollMs = 250) {
  const deadline = Date.now() + timeoutMs;
  let stableSince = null;
  while (Date.now() < deadline) {
    if (statusFn().running) {
      if (stableSince === null) stableSince = Date.now();
      if (Date.now() - stableSince >= stableMs) return true;
    } else {
      stableSince = null;
    }
    await new Promise((resolve15) => setTimeout(resolve15, pollMs));
  }
  return statusFn().running;
}
function stopMw(projectDir) {
  const mwPy = findMwPy();
  if (!mwPy) return false;
  const result = spawn3(PYTHON_EXE, [mwPy, "stop", `--project=${projectDir}`], {
    stdio: "inherit"
  });
  result.unref();
  return true;
}
function serveMetaPath(projectDir) {
  return path17.join(projectDir, ".mw", "serve.meta");
}
function readServeMeta(projectDir) {
  try {
    const raw = fs12.readFileSync(serveMetaPath(projectDir), "utf8");
    const m = JSON.parse(raw);
    if (typeof m.pid !== "number" || typeof m.started_at_ms !== "number") return null;
    return { pid: m.pid, startedAtMs: m.started_at_ms };
  } catch {
    return null;
  }
}
function mwCodeNewestMtimeMs(mwPyOverride) {
  const mwPy = mwPyOverride ?? findMwPy();
  if (!mwPy) return null;
  let newest = 0;
  const walk = (dir) => {
    let entries;
    try {
      entries = fs12.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.isDirectory()) {
        if (e.name === "__pycache__" || e.name === "dist" || e.name === ".tmp") continue;
        walk(path17.join(dir, e.name));
        continue;
      }
      if (!e.isFile()) continue;
      if (!/\.(py|json)$/.test(e.name)) continue;
      if (e.name.startsWith("test_") || e.name.startsWith("_")) continue;
      try {
        const m = fs12.statSync(path17.join(dir, e.name)).mtimeMs;
        if (m > newest) newest = m;
      } catch {
      }
    }
  };
  walk(path17.dirname(mwPy));
  return newest > 0 ? newest : null;
}
function serveStaleness(projectDir, codeMtimeMs) {
  const codeMs = codeMtimeMs ?? mwCodeNewestMtimeMs();
  if (codeMs === null) return void 0;
  let startedAtMs = readServeMeta(projectDir)?.startedAtMs ?? null;
  if (startedAtMs === null) {
    try {
      startedAtMs = fs12.statSync(pidFilePath(projectDir)).mtimeMs;
    } catch {
      return void 0;
    }
  }
  const stale = codeMs > startedAtMs + 2e3;
  return {
    stale,
    detail: `serve started ${new Date(startedAtMs).toISOString()}, mw code changed ${new Date(codeMs).toISOString()}`
  };
}
async function restartSequence(isRunning, requestStop, start, waitUp, timeoutMs, pollMs = 250) {
  if (isRunning()) {
    requestStop();
    const deadline = Date.now() + timeoutMs;
    while (isRunning() && Date.now() < deadline) {
      await new Promise((resolve15) => setTimeout(resolve15, pollMs));
    }
    if (isRunning()) return "stop-failed";
  }
  if (!start()) return "start-failed";
  return await waitUp() ? "restarted" : "start-failed";
}
async function restartMw(projectDir, timeoutMs = 3e4) {
  return restartSequence(
    () => getMwStatus(projectDir).running,
    () => {
      const stopReq = path17.join(projectDir, ".mw", "mw.stop");
      fs12.mkdirSync(path17.dirname(stopReq), { recursive: true });
      fs12.writeFileSync(stopReq, "stop", "utf8");
    },
    () => startMw(projectDir),
    () => waitForMwStart(projectDir),
    timeoutMs
  );
}
function doctorMw(projectDir, fix = false) {
  const mwPy = findMwPy();
  if (!mwPy) return { ok: false, error: "Could not find mw.py \u2014 set MW_PY env var." };
  const args = [mwPy, "doctor", `--project=${projectDir}`, "--json"];
  if (fix) args.push("--fix");
  const result = spawnSync2(PYTHON_EXE, args, { encoding: "utf8", timeout: 15e3 });
  if (result.error) {
    return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
  }
  if (!result.stdout || !result.stdout.trim()) {
    const stderr = result.stderr?.trim() ?? "";
    return { ok: false, error: stderr || `mw doctor exited with code ${result.status}` };
  }
  try {
    return { ok: true, report: JSON.parse(result.stdout) };
  } catch (err) {
    return { ok: false, error: `mw doctor returned non-JSON output: ${String(err)}` };
  }
}
function runMwCliRaw(sub, projectDir, args, timeoutMs = 3e4) {
  const mwPy = findMwPy();
  if (!mwPy) return { code: -1, output: "", spawnError: "Could not find mw.py \u2014 set MW_PY env var." };
  const result = spawnSync2(PYTHON_EXE, [mwPy, sub, ...args, `--project=${projectDir}`], {
    encoding: "utf8",
    timeout: timeoutMs
  });
  if (result.error) {
    return { code: -1, output: "", spawnError: `Failed to spawn mw.py: ${result.error.message}` };
  }
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  return { code: result.status ?? -1, output };
}
function runMwCli(sub, projectDir, args, timeoutMs = 3e4) {
  const raw = runMwCliRaw(sub, projectDir, args, timeoutMs);
  if (raw.spawnError !== void 0) return { ok: false, error: raw.spawnError };
  if (raw.code !== 0) return { ok: false, error: raw.output || `mw ${sub} exited with code ${raw.code}` };
  return { ok: true, output: raw.output };
}
function targetMw(projectDir, args) {
  return runMwCli("target", projectDir, args);
}
function partitionMw(projectDir, args) {
  return runMwCli("partition", projectDir, args);
}
function modelMw(projectDir, args) {
  return runMwCli("model", projectDir, args);
}
var RAG_SUBCOMMANDS = ["list", "probe", "audit", "sync", "init"];
function ragMw(projectDir, args) {
  const raw = runMwCliRaw("rag", projectDir, args);
  if (raw.spawnError !== void 0) return { ok: false, code: raw.code, output: raw.spawnError };
  return { ok: raw.code === 0, code: raw.code, output: raw.output };
}
function updateEnvMw(projectDir, apply) {
  const mwPy = findMwPy();
  if (!mwPy) return { ok: false, error: "Could not find mw.py \u2014 set MW_PY env var." };
  const args = [mwPy, "update-env", `--project=${projectDir}`];
  if (apply) args.push("--apply");
  const result = spawnSync2(PYTHON_EXE, args, { encoding: "utf8", timeout: 6e5 });
  if (result.error) {
    return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
  }
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  if (!output) {
    return { ok: false, error: `mw update-env exited with code ${result.status}` };
  }
  return { ok: true, output };
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts
function agenticScriptsDir(projectDir) {
  const candidates = [
    path18.join(projectDir, ".claude", "scripts"),
    path18.join(projectDir, ".agents", "skills", "agentic-task", "claude", "scripts")
  ];
  for (const dir of candidates) {
    if (fs13.existsSync(path18.join(dir, "advance_phase.py"))) return dir;
  }
  return null;
}
function runAgenticScript(projectDir, scriptName, args, timeoutMs = 3e4) {
  const dir = agenticScriptsDir(projectDir);
  if (!dir) {
    return {
      ok: false,
      output: "AgenticTask framework scripts not found (looked for .claude/scripts/advance_phase.py and .agents/skills/agentic-task/claude/scripts/advance_phase.py under the project root). Run the framework installer (mw setup / install.py) first."
    };
  }
  const script = path18.join(dir, scriptName);
  if (!fs13.existsSync(script)) {
    return { ok: false, output: `Framework script not found: ${script}` };
  }
  const result = spawnSync3(PYTHON_EXE, ["-X", "utf8", script, ...args], {
    cwd: projectDir,
    encoding: "utf8",
    timeout: timeoutMs,
    windowsHide: true
  });
  if (result.error) {
    return {
      ok: false,
      output: `Failed to spawn ${PYTHON_EXE} for ${scriptName}: ${result.error.message}. Install Python and make sure '${PYTHON_EXE}' resolves on this machine's PATH.`
    };
  }
  if (result.status === null) {
    return {
      ok: false,
      output: `${scriptName} was killed before finishing (signal ${result.signal ?? "?"}) \u2014 timeout?`
    };
  }
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  if (result.status !== 0) {
    return { ok: false, output: output || `${scriptName} exited with code ${result.status}` };
  }
  return { ok: true, output: output || "(no output)" };
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/file-lock.ts
import * as fs14 from "node:fs";
import * as path19 from "node:path";
async function acquireLock(lockPath, opts = {}) {
  const retries = opts.retries ?? 10;
  const baseDelayMs = opts.baseDelayMs ?? 50;
  const dir = path19.dirname(lockPath);
  if (!fs14.existsSync(dir)) {
    fs14.mkdirSync(dir, { recursive: true });
  }
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const fd = fs14.openSync(lockPath, "wx");
      fs14.closeSync(fd);
      return () => {
        try {
          fs14.unlinkSync(lockPath);
        } catch {
        }
      };
    } catch (err) {
      const isExist = err instanceof Error && "code" in err && err.code === "EEXIST";
      if (!isExist) throw err;
      if (attempt === retries) {
        throw new Error(`Could not acquire lock at ${lockPath} after ${retries} retries`);
      }
      await sleep(baseDelayMs * 2 ** attempt);
    }
  }
  throw new Error(`Could not acquire lock at ${lockPath}`);
}
function sleep(ms) {
  return new Promise((resolve15) => setTimeout(resolve15, ms));
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts
import * as fs15 from "node:fs";
import * as path20 from "node:path";
var INDEX_COLS = 7;
function parseIndexLine(line) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) return void 0;
  let parts;
  if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
    parts = trimmed.slice(1, -1).split("|").map((s) => s.trim());
  } else {
    parts = trimmed.split("|").map((s) => s.trim());
  }
  if (parts.length !== INDEX_COLS) return void 0;
  const [key, status, phase, claimId, deps, desc, updated] = parts;
  if (!key || key.startsWith("#") || key.startsWith("-") || key === "Key" || key.startsWith("---")) return void 0;
  return {
    key,
    status: status ?? "idle",
    phase: phase ?? "",
    claimId: claimId ?? "",
    deps: deps ?? "",
    desc: desc ?? "",
    updated: updated ?? ""
  };
}
function serializeIndexLine(entry) {
  return `| ${[entry.key, entry.status, entry.phase, entry.claimId, entry.deps, entry.desc, entry.updated].join(" | ")} |`;
}
var IndexStore = class {
  constructor(agenticdocRoot2) {
    this.filePath = path20.join(agenticdocRoot2, "_index.parallel");
    this.lockPath = path20.join(agenticdocRoot2, "..", ".mw", "index.lock");
  }
  readAll() {
    if (!fs15.existsSync(this.filePath)) return [];
    const lines = fs15.readFileSync(this.filePath, "utf8").split("\n");
    return lines.map(parseIndexLine).filter((e) => e !== void 0);
  }
  async upsert(entry) {
    const release = await acquireLock(this.lockPath);
    try {
      const existing = this.readAll();
      const idx = existing.findIndex((e) => e.key === entry.key);
      if (idx >= 0) {
        existing[idx] = entry;
      } else {
        existing.push(entry);
      }
      this.writeRows(existing);
    } finally {
      release();
    }
  }
  /** Atomically claim `key` for `self`: liveness check, optional demote of
   * other active rows, upsert, and a post-write disk verification — all
   * under ONE lock acquisition, so racing windows cannot both walk away
   * believing they hold the claim. `heldLive` decides whether a foreign
   * claim blocks us (ui-bridge claimState; injected to keep this store free
   * of host/os dependencies). */
  async claim(key, self, heldLive, opts = {}) {
    const { force = false, demoteOthers = true, activate: activate2 = true } = opts;
    const release = await acquireLock(this.lockPath);
    try {
      const rows = this.readAll();
      const idx = rows.findIndex((e) => e.key === key);
      const existing = rows[idx];
      if (existing && existing.claimId !== self && heldLive(existing.claimId) && !force) {
        return { ok: false, blockedBy: existing.claimId, entry: existing, created: false };
      }
      const now = (/* @__PURE__ */ new Date()).toISOString();
      if (demoteOthers) {
        for (let i = 0; i < rows.length; i++) {
          if (rows[i].status === "active" && rows[i].key !== key) {
            rows[i] = { ...rows[i], status: "idle", updated: now };
          }
        }
      }
      const claimed = existing ? {
        ...existing,
        claimId: self,
        updated: now,
        ...activate2 ? { status: "active" } : {}
      } : { key, status: "active", phase: "SPEC", claimId: self, deps: "", desc: "", updated: now };
      if (idx >= 0) rows[idx] = claimed;
      else rows.push(claimed);
      this.writeRows(rows);
      const after = this.findByKey(key);
      if (!after || after.claimId !== self) {
        return { ok: false, blockedBy: after?.claimId, entry: after ?? claimed, created: false };
      }
      return { ok: true, entry: after, created: !existing };
    } finally {
      release();
    }
  }
  /** Serialize rows back to _index.parallel, preserving AgenticTask header
   * lines. Callers must hold the index lock. */
  writeRows(rows) {
    let header = "";
    if (fs15.existsSync(this.filePath)) {
      const raw = fs15.readFileSync(this.filePath, "utf8");
      const headerLines = [];
      for (const l of raw.split("\n")) {
        const t = l.trim();
        if (t.startsWith("#") || t.startsWith("| Key") || t.startsWith("| ---") || t.startsWith("|---")) {
          headerLines.push(l);
        } else {
          break;
        }
      }
      if (headerLines.length > 0) {
        header = `${headerLines.join("\n")}
`;
      }
    }
    const content = `${header}${rows.map(serializeIndexLine).join("\n")}
`;
    const tmpPath = `${this.filePath}.tmp`;
    fs15.writeFileSync(tmpPath, content, "utf8");
    fs15.renameSync(tmpPath, this.filePath);
  }
  findByKey(key) {
    return this.readAll().find((e) => e.key === key);
  }
  /** The currently active row, if any (single-active discipline).
   * Legacy divergence can leave several active rows; the most recently
   * updated one wins (ties: the later row in file order). TS rows carry
   * ISO-UTC `updated` while update_index.py writes local "YYYY-MM-DD HH:MM",
   * so compare via Date.parse rather than lexicographic order. Exposes the
   * full row so callers can also read its claimId (owner resolution must
   * distinguish "our" active row from another live window's). */
  activeEntry() {
    let best;
    let bestTs = Number.NEGATIVE_INFINITY;
    for (const e of this.readAll()) {
      if (e.status !== "active") continue;
      const parsed = Date.parse(e.updated);
      const ts = Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
      if (!best || ts >= bestTs) {
        best = e;
        bestTs = ts;
      }
    }
    return best;
  }
  activeKey() {
    return this.activeEntry()?.key;
  }
};
function readIndexMdActive(agenticdocRoot2) {
  const mdPath = path20.join(agenticdocRoot2, "_index.md");
  if (!fs15.existsSync(mdPath)) return void 0;
  for (const line of fs15.readFileSync(mdPath, "utf8").split("\n")) {
    const m = /^active:\s*(\S+)/u.exec(line.trim());
    if (m) return m[1];
  }
  return void 0;
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts
import * as fs17 from "node:fs";
import * as path21 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/pm/goal-reader.ts
import * as fs16 from "node:fs";
function parseStatus(content) {
  const m = content.match(/^\s*>?\s*status:\s*(\w+)/im);
  if (!m) return "unknown";
  const v = m[1].toLowerCase();
  if (v === "draft") return "draft";
  if (v === "active") return "active";
  return "unknown";
}
function parseGoalMd(content) {
  const section = (heading) => {
    const re = new RegExp(`## ${heading}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`, "i");
    const m = content.match(re);
    return m ? m[1].trim() : "";
  };
  const clean = (s) => s.replace(/<!--[\s\S]*?-->/g, "").trim();
  return {
    status: parseStatus(content),
    goal: clean(section("Goal")),
    context: clean(section("Context")),
    keyConstraints: clean(section("Key Constraints"))
  };
}
function readGoal(agenticdocRoot2) {
  const resolved = goalPath(agenticdocRoot2);
  if (!fs16.existsSync(resolved)) return null;
  try {
    return parseGoalMd(fs16.readFileSync(resolved, "utf8"));
  } catch {
    return null;
  }
}
function isGoalEstablished(goal) {
  if (!goal) return false;
  if (goal.status === "active") return true;
  if (goal.status === "draft") return false;
  return Boolean(goal.goal || goal.context || goal.keyConstraints);
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts
var MIN_PHASE_DOC_BYTES = 500;
function fileAtLeast(file, minBytes) {
  try {
    return fs17.statSync(file).size >= minBytes;
  } catch {
    return false;
  }
}
function countNotes(dir, prefix) {
  try {
    return fs17.readdirSync(dir).filter((n) => n.startsWith(prefix) && n.endsWith(".md")).length;
  } catch {
    return 0;
  }
}
function hasSectionWith(text, headingKws, mustContain) {
  const stripped = text.replace(/<!--[\s\S]*?-->/g, "");
  const lines = stripped.split("\n");
  let inSection = false;
  let level = 0;
  const body = [];
  for (const line of lines) {
    const m = /^(#{1,6})\s/.exec(line);
    if (m) {
      const lv = m[1].length;
      if (inSection && lv <= level) break;
      if (!inSection && headingKws.some((kw) => line.includes(kw))) {
        inSection = true;
        level = lv;
      }
      continue;
    }
    if (inSection) body.push(line);
  }
  const joined = body.join("\n").trim();
  return joined.length > 0 && (mustContain === void 0 || joined.includes(mustContain));
}
function readSpecContent(keyDir) {
  try {
    return fs17.readFileSync(path21.join(keyDir, "spec.md"), "utf8");
  } catch {
    return void 0;
  }
}
function readPhaseDocs(agenticdocRoot2, key) {
  const keyDir = path21.join(agenticdocRoot2, key);
  const specContent = readSpecContent(keyDir);
  const goalEstablished = isGoalEstablished(readGoal(agenticdocRoot2));
  return {
    spec: fileAtLeast(path21.join(keyDir, "spec.md"), MIN_PHASE_DOC_BYTES),
    design: fileAtLeast(path21.join(keyDir, "design.md"), MIN_PHASE_DOC_BYTES),
    specEvidence: countNotes(path21.join(keyDir, "evidence", "research"), "spec-"),
    designEvidence: countNotes(path21.join(keyDir, "evidence", "research"), "design-"),
    specS0: !goalEstablished || hasSectionWith(specContent ?? "", ["\xA70", "Goal Alignment"], "\u9884\u671F\u6536\u76CA"),
    specAC: /AC-\d{3}/.test(specContent ?? "")
  };
}
function phaseDocGaps(status) {
  const gaps = [];
  if (!status.spec) gaps.push("spec.md missing or under 500 bytes");
  if (status.specEvidence < 1)
    gaps.push("evidence/research/spec-*.md missing (>= 1 research note; a zero-research declaration counts)");
  if (!status.specS0)
    gaps.push("spec.md missing a non-empty \xA70 Goal Alignment section with \u9884\u671F\u6536\u76CA (goal.md is established)");
  if (!status.specAC) gaps.push("spec.md has no numbered acceptance criteria (AC-NNN)");
  if (!status.design) gaps.push("design.md missing or under 500 bytes");
  if (status.designEvidence < 1)
    gaps.push("evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)");
  return gaps;
}
function formatDocsBadge(status) {
  const ev = (status.specEvidence >= 1 ? 1 : 0) + (status.designEvidence >= 1 ? 1 : 0);
  return `S${status.spec ? "+" : "-"} D${status.design ? "+" : "-"} ev:${ev}/2`;
}
var DOC_GATE_HINT = "Generate them via the agentic-task requirements/system-design workflows (every key decision needs an evidence/research/ note; zero-research still needs a declaration note). For throwaway ad-hoc work, dispatch under '_scratch' instead.";
function dispatchDocGaps(agenticdocRoot2, key) {
  if (key === SCRATCH_WORKERS_KEY) return [];
  return phaseDocGaps(readPhaseDocs(agenticdocRoot2, key));
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-guard.ts
import * as fs18 from "node:fs";
import * as path22 from "node:path";
var INTERFACE_LINE = /^- (Phase|Claim-Id):/m;
var PHASE_LINE = /^- Phase:\s*(.+?)\s*$/m;
var PHASE_ORDER = ["SPEC", "DESIGN", "PLAN", "TASKS", "EXECUTE", "VERIFY", "DONE"];
var PHASE_GUARD_HINT = "pm-state.md's '- Phase:' and '- Claim-Id:' lines are machine interfaces owned by the framework scripts (advance_phase.py / update_index.py); hand-editing them bypasses the phase gates. To change phase, call the advance_phase tool (shell-free) or run: python <framework>/scripts/advance_phase.py <key> <target-phase> (gates are checked, pm-state and _index.parallel stay in sync). To update the rest of pm-state.md (logs, ledgers, decisions), keep the interface lines byte-identical.";
function interfaceLines(content) {
  return content.split("\n").filter((l) => INTERFACE_LINE.test(l));
}
function pmStateTarget(toolName, args, projectDir, agenticdocRoot2) {
  if (toolName !== "write" && toolName !== "edit") return void 0;
  const filePath = args?.path;
  if (typeof filePath !== "string" || filePath === "") return void 0;
  const rel = path22.relative(path22.resolve(agenticdocRoot2), path22.resolve(projectDir, filePath));
  if (rel.startsWith("..") || path22.isAbsolute(rel)) return void 0;
  const parts = rel.split(path22.sep);
  if (parts.length !== 2 || parts[1] !== "pm-state.md") return void 0;
  const key = parts[0] ?? "";
  if (!key || key.startsWith("_") || key.startsWith(".")) return void 0;
  return { key, absPath: path22.resolve(projectDir, filePath) };
}
function pmStateInterfaceViolation(toolName, args, projectDir, agenticdocRoot2, readFile = defaultReadFile) {
  const target = pmStateTarget(toolName, args, projectDir, agenticdocRoot2);
  if (!target) return void 0;
  if (toolName === "write") {
    const content = args?.content;
    if (typeof content !== "string") return void 0;
    const next = interfaceLines(content);
    if (next.length === 0) return void 0;
    const cur = interfaceLines(readFile(target.absPath) ?? "");
    if (cur.length === next.length && cur.every((l, i) => l === next[i])) return void 0;
    return `${PHASE_GUARD_HINT} (key: ${target.key})`;
  }
  const edits = args?.edits;
  if (!Array.isArray(edits)) return void 0;
  for (const e of edits) {
    const oldText = e?.oldText;
    const newText = e?.newText;
    if (typeof oldText === "string" && INTERFACE_LINE.test(oldText) || typeof newText === "string" && INTERFACE_LINE.test(newText)) {
      return `${PHASE_GUARD_HINT} (key: ${target.key})`;
    }
  }
  return void 0;
}
function defaultReadFile(abs) {
  try {
    return fs18.readFileSync(abs, "utf8");
  } catch {
    return void 0;
  }
}
function registerPmStateGuard(pi, projectDir, agenticdocRoot2) {
  pi.on("tool_call", (event) => {
    if (event.toolName !== "write" && event.toolName !== "edit") return void 0;
    const reason = pmStateInterfaceViolation(event.toolName, event.input, projectDir, agenticdocRoot2);
    return reason ? { block: true, reason } : void 0;
  });
}
function readPmStatePhase(agenticdocRoot2, key) {
  try {
    const content = fs18.readFileSync(path22.join(agenticdocRoot2, key, "pm-state.md"), "utf8");
    const m = PHASE_LINE.exec(content);
    return m?.[1];
  } catch {
    return void 0;
  }
}
function phaseAuditWarnings(agenticdocRoot2, key, indexPhase) {
  if (key === SCRATCH_WORKERS_KEY) return [];
  const warnings = [];
  const pmPhase = readPmStatePhase(agenticdocRoot2, key);
  if (!pmPhase || pmPhase === "(pending)" || pmPhase.toUpperCase() === "INIT") return warnings;
  const upper = pmPhase.toUpperCase();
  const rank = PHASE_ORDER.indexOf(upper);
  if (rank < 0) {
    warnings.push(`[audit] pm-state.md has unknown phase '${pmPhase}' (valid: ${PHASE_ORDER.join("/")}).`);
    return warnings;
  }
  if (indexPhase && indexPhase !== "\u2014" && indexPhase.toUpperCase() !== upper) {
    warnings.push(
      `[audit] INDEX-DIVERGENCE: pm-state.md phase=${upper} != _index.parallel phase=${indexPhase} \u2014 phase changes must go through advance_phase.py (it syncs both sources); divergence means a hand-edit bypassed the gates.`
    );
  }
  const docs = readPhaseDocs(agenticdocRoot2, key);
  if (rank >= PHASE_ORDER.indexOf("DESIGN")) {
    if (!docs.spec) warnings.push("[audit] design gate: spec.md missing or under 500 bytes.");
    if (docs.specEvidence < 1)
      warnings.push(
        "[audit] design gate: evidence/research/spec-*.md missing (>= 1 note; zero-research declaration counts)."
      );
    if (!docs.specS0)
      warnings.push(
        "[audit] design gate: spec.md missing a non-empty \xA70 Goal Alignment section with \u9884\u671F\u6536\u76CA (goal.md is established)."
      );
    if (!docs.specAC) warnings.push("[audit] design gate: spec.md has no numbered acceptance criteria (AC-NNN).");
  }
  if (rank >= PHASE_ORDER.indexOf("PLAN")) {
    if (!docs.design) warnings.push("[audit] plan gate: design.md missing or under 500 bytes.");
    if (docs.designEvidence < 1)
      warnings.push(
        "[audit] plan gate: evidence/research/design-*.md missing (>= 1 note; zero-research declaration counts)."
      );
  }
  if (rank >= PHASE_ORDER.indexOf("EXECUTE")) {
    try {
      const n = fs18.readdirSync(path22.join(agenticdocRoot2, key, "tasks")).filter((f) => f.endsWith(".md")).length;
      if (n < 1) warnings.push("[audit] execute gate: tasks/ has no .md files.");
    } catch {
      warnings.push(
        "[audit] execute gate: tasks/ directory missing (mw-dispatch flows: keep a pointer task.md under tasks/ so the key stays auditable)."
      );
    }
  }
  return warnings;
}

// packages/coding-agent/src/extensions/agent-team-loop/pm/state-manager.ts
import * as fs19 from "node:fs";
import * as path23 from "node:path";
var VALID_PHASES = /* @__PURE__ */ new Set(["SPEC", "DESIGN", "PLAN", "TASKS", "EXECUTE", "DONE"]);
var StateManager = class {
  constructor(agenticdocRoot2, taskKey) {
    this.statePath = path23.join(agenticdocRoot2, taskKey, "pm-state.md");
  }
  read() {
    if (!fs19.existsSync(this.statePath)) return {};
    const content = fs19.readFileSync(this.statePath, "utf8");
    const state = {};
    for (const line of content.split("\n")) {
      const m = line.match(/^- Phase:\s*(.+)$/);
      if (m) state.phase = m[1].trim();
      const m2 = line.match(/^- Claim-Id:\s*(.+)$/);
      if (m2) state.claimId = m2[1].trim();
    }
    return state;
  }
  async write(state) {
    if (state.phase !== void 0 && !VALID_PHASES.has(state.phase)) {
      throw new Error(`Invalid phase: ${state.phase}. Valid values: ${[...VALID_PHASES].join(", ")}`);
    }
    const current = this.read();
    const merged = {
      phase: state.phase ?? current.phase ?? "SPEC",
      claimId: state.claimId ?? current.claimId ?? "",
      taskKey: state.taskKey ?? current.taskKey ?? "",
      notes: state.notes ?? current.notes ?? "",
      updatedAt: (/* @__PURE__ */ new Date()).toISOString()
    };
    const content = [
      `# PM State: ${merged.taskKey}`,
      "",
      "## Section 1: Snapshot",
      `- Key: ${merged.taskKey}`,
      `- Claim-Id: ${merged.claimId}`,
      `- Phase: ${merged.phase}`,
      `- Updated: ${merged.updatedAt}`,
      "",
      "## Notes",
      "",
      merged.notes
    ].join("\n");
    const dir = path23.dirname(this.statePath);
    fs19.mkdirSync(dir, { recursive: true });
    const lockPath = `${this.statePath}.lock`;
    const release = await acquireLock(lockPath);
    try {
      const tmpPath = `${this.statePath}.tmp`;
      fs19.writeFileSync(tmpPath, content, "utf8");
      fs19.renameSync(tmpPath, this.statePath);
    } finally {
      release();
    }
  }
};

// packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts
import * as fs20 from "node:fs";
import * as path24 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/rag/block.ts
var RAG_MARKER_V1 = "<!-- mw-rag: v1 -->";
var RAG_CITATION_SYNTAX = "<server>:<source>:<file_path>:<line>";
function positiveInt(value) {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) return value;
  return null;
}
function resolveBudget(explicit, roleValue, globalValue, fallback) {
  return positiveInt(explicit) ?? positiveInt(roleValue) ?? positiveInt(globalValue) ?? fallback;
}
function renderRagBlock(config, meta) {
  const enabled = config.enabled.filter((name) => typeof name === "string" && name.trim().length > 0);
  if (enabled.length === 0) return null;
  const type = meta.type ?? "";
  const role = meta.role ?? roleForTaskType(type);
  const phase = meta.phase ?? "";
  const roleSpec = config.roles[role];
  const { server, source, rewrite } = resolveDefaults(config, role, phase);
  const lines = [RAG_MARKER_V1, `[mw] RAG enabled: ${enabled.join(", ")}`];
  const requiredRoles = Object.entries(config.roles).filter(([, spec]) => spec.require === true).map(([name]) => name).sort();
  if (requiredRoles.length > 0) lines.push(`[mw] Required roles: ${requiredRoles.join(", ")}`);
  const requiredPhases = Object.entries(config.phases).filter(([, spec]) => spec.require === true).map(([name]) => name).sort();
  if (requiredPhases.length > 0) lines.push(`[mw] Required phases: ${requiredPhases.join(", ")}`);
  lines.push(`[mw] Default server: ${server ?? "none"}`);
  lines.push(`[mw] Default source: ${source ?? "none"}`);
  lines.push(`[mw] Rewrite: ${rewrite ? "true" : "false"}`);
  lines.push(
    `[mw] Chat budget: ${resolveBudget(meta.chatBudget, roleSpec?.chatBudget, config.budgets.chat, DEFAULT_RAG_CHAT_BUDGET)}`
  );
  lines.push(
    `[mw] Time budget: ${resolveBudget(meta.timeBudgetS, roleSpec?.timeBudgetS, config.budgets.timeS, DEFAULT_RAG_TIME_BUDGET_S)}s`
  );
  lines.push(`[mw] Citation syntax: ${RAG_CITATION_SYNTAX}`);
  lines.push(`fingerprint=${config.fingerprint.length > 0 ? config.fingerprint : ragFingerprint(config, enabled)}`);
  return lines.join("\n");
}

// packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts
var PROFILE_MARK = "<!-- mw-profile: v1 -->";
var PROFILE_MARK_V2 = "<!-- mw-profile: v2 -->";
function hasProfileContent(config) {
  return config.mode === "dual" || Object.keys(config.toolchain).length > 0 || config.ignore.deny_globs.length > 0 || config.contract.forbidden_paths.length > 0 || config.contract.conventions !== null || config.contract.docs.length > 0;
}
function renderProfileBlock(config, ignoreEnforced) {
  const lines = [
    PROFILE_MARK,
    "[mw] Workspace profile (target.yml essentials, injected at dispatch;",
    `full file: ${path24.join(config.controlRoot, ".agenticdoc", "target.yml")})`
  ];
  if (config.mode === "dual") {
    lines.push(`Control workspace: ${config.controlRoot}`);
    lines.push(`Game root: ${config.gameRoot}`);
    if (config.engineRoot !== null) lines.push(`Engine root: ${config.engineRoot}`);
  }
  const toolNames = Object.keys(config.toolchain);
  if (toolNames.length > 0) {
    lines.push("Toolchain commands (placeholders resolved):");
    for (const name of toolNames) {
      lines.push(`- ${name}: ${renderToolchainCommand(config.toolchain[name], config)}`);
    }
  }
  if (ignoreEnforced && config.ignore.deny_globs.length > 0) {
    lines.push("Context firewall (deny globs, enforced by the read-scope layer):");
    for (const glob of config.ignore.deny_globs) lines.push(`- ${glob}`);
  }
  const contract = config.contract;
  if (contract.forbidden_paths.length > 0 || contract.conventions !== null || contract.docs.length > 0) {
    lines.push("Contract:");
    if (contract.forbidden_paths.length > 0) {
      lines.push(`- forbidden paths: ${contract.forbidden_paths.join(", ")}`);
    }
    if (contract.conventions !== null) {
      lines.push("- conventions:");
      for (const line of contract.conventions.split("\n")) lines.push(`  ${line}`);
    }
    if (contract.docs.length > 0) {
      lines.push("- docs (references, not inlined):");
      for (const doc of contract.docs) lines.push(`  - ${path24.resolve(config.controlRoot, doc)}`);
    }
  }
  return lines.join("\n");
}
function findProfileBlock(content) {
  const v1 = content.indexOf(PROFILE_MARK);
  const v2 = content.indexOf(PROFILE_MARK_V2);
  if (v1 === -1 && v2 === -1) return null;
  if (v2 === -1) return v1;
  if (v1 === -1) return v2;
  return Math.min(v1, v2);
}
function stripRagBlock(content) {
  const index = content.indexOf(RAG_MARKER_V1);
  if (index === -1) return content;
  return content.slice(0, index).replace(/\s+$/, "\n");
}
function headerInt(content, header) {
  const match2 = new RegExp(`^${header}[ \\t]*(\\d+)[ \\t]*$`, "m").exec(content);
  if (match2 === null) return void 0;
  const value = Number(match2[1]);
  return Number.isFinite(value) && value > 0 ? value : void 0;
}
function parseRagTaskMeta(content) {
  return {
    type: /^type:[ \t]*(.+?)[ \t]*$/m.exec(content)?.[1],
    phase: /^phase:[ \t]*(.+?)[ \t]*$/m.exec(content)?.[1],
    chatBudget: headerInt(content, "rag_chat_budget:"),
    timeBudgetS: headerInt(content, "rag_time_budget_s:")
  };
}
function blockIsFresh(existingText, config) {
  if (config.mode === "partition") {
    return existingText === `${renderPartitionProfileBlock(config, true)}
` || existingText === `${renderPartitionProfileBlock(config, false)}
`;
  }
  if (!hasProfileContent(config)) return false;
  return existingText === `${renderProfileBlock(config, true)}
` || existingText === `${renderProfileBlock(config, false)}
`;
}
function renderPartitionProfileBlock(config, ignoreEnforced) {
  const lines = [
    PROFILE_MARK_V2,
    `[mw] mode: ${config.mode}`,
    "[mw] Workspace profile (target.yml essentials, injected at dispatch;",
    `full file: ${path24.join(config.controlRoot, ".agenticdoc", "target.yml")})`,
    `Control workspace: ${config.controlRoot}`,
    `Parent root (extended workspace, writable): ${config.parentRoot}`,
    `Partition root (worker cwd): ${config.partitionRoot}`
  ];
  const roots = config.roots ?? {};
  if (Object.keys(roots).length > 0) {
    lines.push("Named roots:");
    for (const [name, root] of Object.entries(roots)) lines.push(`- ${name}: ${root}`);
  }
  const toolNames = Object.keys(config.toolchain);
  if (toolNames.length > 0) {
    lines.push("Toolchain commands (placeholders resolved):");
    for (const name of toolNames) {
      lines.push(`- ${name}: ${renderToolchainCommand(config.toolchain[name], config)}`);
    }
  }
  if (ignoreEnforced && config.ignore.deny_globs.length > 0) {
    lines.push("Context firewall (deny globs, enforced by the read-scope layer):");
    for (const glob of config.ignore.deny_globs) lines.push(`- ${glob}`);
  }
  const contract = config.contract;
  if (contract.forbidden_paths.length > 0 || contract.conventions !== null || contract.docs.length > 0) {
    lines.push("Contract:");
    if (contract.forbidden_paths.length > 0) {
      lines.push(`- forbidden paths: ${contract.forbidden_paths.join(", ")}`);
    }
    if (contract.conventions !== null) {
      lines.push("- conventions:");
      for (const line of contract.conventions.split("\n")) lines.push(`  ${line}`);
    }
    if (contract.docs.length > 0) {
      lines.push("- docs (references, not inlined):");
      for (const doc of contract.docs) lines.push(`  - ${path24.resolve(config.controlRoot, doc)}`);
    }
  }
  return lines.join("\n");
}
function insertDenyGlobs(content, denyGlobs) {
  const block = ["deny_globs:", ...denyGlobs.map((g) => `  - '${g}'`)].join("\n");
  const lines = content.split("\n");
  if (lines[0]?.trim() === "---") {
    const close = lines.findIndex((line, i) => i > 0 && line.trim() === "---");
    if (close !== -1) {
      lines.splice(close, 0, block);
      return lines.join("\n");
    }
  }
  return `${block}
${content}`;
}
function injectWorkspaceProfile(taskPath) {
  const controlRoot = controlRootFromTaskPath(taskPath);
  const config = resolveWorkspaceConfig(controlRoot);
  let original;
  try {
    original = fs20.readFileSync(taskPath, "utf8");
  } catch (err) {
    console.error(
      `[mw] profile injection skipped for ${taskPath}: ${err instanceof Error ? err.message : String(err)}`
    );
    return;
  }
  const base = stripRagBlock(original);
  const existing = findProfileBlock(base);
  const ownDenyGlobs = /^deny_globs:/m.test(base);
  let out = base;
  const profileFresh = existing !== null && blockIsFresh(base.slice(existing).replace(/\s+$/, "\n"), config);
  if (!profileFresh) {
    out = existing !== null ? base.slice(0, existing).replace(/\s+$/, "\n") : base;
    if (config.ignore.deny_globs.length > 0 && !ownDenyGlobs) {
      out = insertDenyGlobs(out, config.ignore.deny_globs);
    }
    if (config.mode === "partition") {
      out = `${out.replace(/\s+$/, "\n")}
${renderPartitionProfileBlock(config, !ownDenyGlobs)}
`;
    } else if (hasProfileContent(config)) {
      out = `${out.replace(/\s+$/, "\n")}
${renderProfileBlock(config, !ownDenyGlobs)}
`;
    }
  }
  const ragBlock = renderRagBlock(loadRagConfig(controlRoot), parseRagTaskMeta(base));
  if (ragBlock !== null) out = `${out.replace(/\s+$/, "")}

${ragBlock}
`;
  if (out !== original) fs20.writeFileSync(taskPath, out, "utf8");
}
async function dispatchTask(entry, store) {
  injectWorkspaceProfile(entry.taskPath);
  const now = (/* @__PURE__ */ new Date()).toISOString();
  const full = {
    ...entry,
    dispatchedAt: now,
    updatedAt: now
  };
  await store.upsert(full);
}

// packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
function resolveOwnerKeyWithSync(pi, indexStore, watch, explicit, agenticdocRoot2) {
  const explicitKey = (explicit ?? "").trim();
  if (explicitKey) return explicitKey;
  const self = windowClaimId();
  if (watch.key) {
    if (watch.key === SCRATCH_WORKERS_KEY) return watch.key;
    if (indexStore.findByKey(watch.key)?.claimId === self) return watch.key;
  }
  const active = indexStore.activeEntry();
  if (active && claimState(active.claimId, self) === "held-live") {
    warnForeignActiveOnce(pi, active.key);
    return SCRATCH_WORKERS_KEY;
  }
  const owner = active?.key ?? readIndexMdActive(agenticdocRoot2) ?? SCRATCH_WORKERS_KEY;
  if (watch.key && watch.key !== owner) warnOwnerMismatchOnce(pi, watch.key, owner);
  return owner;
}
var warnedOwnerMismatches = /* @__PURE__ */ new Set();
function warnOwnerMismatchOnce(pi, watchKey, ownerKey) {
  const pair = `${watchKey}->${ownerKey}`;
  if (warnedOwnerMismatches.has(pair)) return;
  warnedOwnerMismatches.add(pair);
  displaySummary(
    pi,
    `[mw] owner-key mismatch: this window watches '${watchKey}' but holds no claim on it, and the active key is '${ownerKey}' \u2014 dispatching under '${ownerKey}'. Run /pm-key switch ${ownerKey} to align the window.`
  );
}
var warnedForeignActives = /* @__PURE__ */ new Set();
function warnForeignActiveOnce(pi, activeKey) {
  if (warnedForeignActives.has(activeKey)) return;
  warnedForeignActives.add(activeKey);
  displaySummary(
    pi,
    `[mw] active key '${activeKey}' is claimed by another live window \u2014 not dispatching under it; using '${SCRATCH_WORKERS_KEY}' instead. Pass an explicit key, or switch_key in this window first.`
  );
}
function displaySummary(pi, summary) {
  pi.sendMessage({
    customType: "agent-team-loop:worker-summary",
    content: summary,
    display: true,
    details: summary
  });
}
function deliverPmAlert(pi, text) {
  pi.sendMessage(
    {
      customType: "agent-team-loop:worker-summary",
      content: text,
      display: true,
      details: text
    },
    { triggerTurn: true }
  );
}
function deliverWorkerResult(pi, summary) {
  deliverPmAlert(pi, summary);
}
var WATCH_ENTRY_TYPE = "agent-team-loop:watch";
function windowClaimId() {
  return `${os3.hostname()}:${process.pid}`;
}
function parseClaim(claimId) {
  const m = claimId.match(/^([^:]+):(\d+)$/);
  if (!m) return void 0;
  const pid = Number(m[2]);
  if (!Number.isInteger(pid) || pid <= 0) return void 0;
  return { host: m[1] ?? "", pid };
}
function isPidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === "EPERM";
  }
}
function claimState(claimId, self) {
  const trimmed = claimId.trim();
  if (!trimmed || trimmed === self) return "free";
  const c = parseClaim(trimmed);
  if (!c) return "free";
  if (c.host !== os3.hostname()) return "held-live";
  return isPidAlive(c.pid) ? "held-live" : "held-stale";
}
async function takeOverKey(indexStore, key, force, agenticdocRoot2) {
  const self = windowClaimId();
  const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", { force });
  const audit = outcome.ok ? phaseAuditWarnings(agenticdocRoot2, key, outcome.entry.phase) : [];
  return { ok: outcome.ok, blockedBy: outcome.blockedBy, claimId: self, created: outcome.created, audit };
}
var WATCH_WIDGET_KEY = "agent-team-loop-watch";
var WATCH_HISTORY_MAX = 5;
var WATCH_LINE_MAX = 110;
var STATUS_GLYPH = {
  pending: ".",
  running: ">",
  done: "+",
  failed: "x",
  "needs-clarification": "?"
};
function trunc(s, max) {
  return s.length <= max ? s : `${s.slice(0, max - 1)}\u2026`;
}
function ownerKeyOf(entry, agenticdocRoot2) {
  const rel = path25.relative(agenticdocRoot2, path25.normalize(entry.taskPath));
  return rel.split(path25.sep)[0] ?? "";
}
function readOutputSection(taskDir, section) {
  let content;
  try {
    content = fs21.readFileSync(path25.join(taskDir, "output.md"), "utf8");
  } catch {
    return void 0;
  }
  const m = content.match(
    new RegExp(`## ${section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n+([\\s\\S]*?)(?=\\n## |$)`)
  );
  return m ? m[1].trim() : void 0;
}
function readOutputSummary(taskDir) {
  return readOutputSection(taskDir, "Summary");
}
var OUTPUT_READBACK_MAX = 2e4;
function readOutputBody(taskDir) {
  const outputPath = path25.join(taskDir, "output.md");
  let content;
  try {
    content = fs21.readFileSync(outputPath, "utf8").trim();
  } catch {
    return void 0;
  }
  if (!content) return void 0;
  if (content.length <= OUTPUT_READBACK_MAX) return content;
  return `${content.slice(0, OUTPUT_READBACK_MAX)}

\u2026(truncated \u2014 full report: ${outputPath})`;
}
function readSpawnFailure(taskDir) {
  const logPath = path25.join(taskDir, "worker.log");
  try {
    const stat = fs21.statSync(logPath);
    if (stat.size > 64 * 1024) return void 0;
    const lines = fs21.readFileSync(logPath, "utf8").split("\n");
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (line.startsWith("[launcher] spawn failed")) return line;
    }
    return void 0;
  } catch {
    return void 0;
  }
}
var WORKER_LOG_TAIL_MAX = 256 * 1024;
function readWorkerLogTail(taskDir) {
  try {
    const stat = fs21.statSync(path25.join(taskDir, "worker.log"));
    if (stat.size > WORKER_LOG_TAIL_MAX) return void 0;
    const lines = fs21.readFileSync(path25.join(taskDir, "worker.log"), "utf8").split("\n");
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (line !== "") return line;
    }
    return void 0;
  } catch {
    return void 0;
  }
}
var DETAIL_MARKER_RE = /^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/;
function firstLine(body) {
  let line = body?.split("\n")[0]?.trim() ?? "";
  while (DETAIL_MARKER_RE.test(line)) {
    line = line.replace(DETAIL_MARKER_RE, "").trim();
  }
  return line === "" ? void 0 : line;
}
function readTerminalDetail(taskDir, status) {
  if (status === "failed") {
    const spawn4 = readSpawnFailure(taskDir);
    if (spawn4 !== void 0) {
      const reason = spawn4.match(/^\[launcher\] spawn failed \([^)]*\):\s*(.*)$/);
      return (reason?.[1] ?? spawn4).trim();
    }
    return firstLine(readOutputSection(taskDir, "Exit Reason")) ?? "";
  }
  if (status === "needs-clarification") {
    return firstLine(readOutputSection(taskDir, "Questions")) ?? readWorkerLogTail(taskDir) ?? "no output.md";
  }
  if (status === "done") {
    const tldr = firstLine(readOutputSection(taskDir, "TL;DR"));
    if (tldr !== void 0) return tldr;
    const summary = readOutputSummary(taskDir);
    return summary === void 0 ? "" : headline(summary);
  }
  return "";
}
function isTerminalStatus(status) {
  return status === "done" || status === "failed" || status === "needs-clarification";
}
async function ackTasks(workerStore, ackStore, targets) {
  const entries = workerStore.readAll();
  if (targets === "all") {
    const alreadyAcked = new Set(ackStore.readAll().keys());
    const keys = entries.filter((e) => isTerminalStatus(e.status) && !alreadyAcked.has(e.taskKey)).map((e) => e.taskKey);
    if (keys.length === 0) return { acked: [], rejected: [] };
    return { acked: (await ackStore.ack(keys)).acked, rejected: [] };
  }
  const byKey = new Map(entries.map((e) => [e.taskKey, e]));
  const acked = [];
  const rejected = [];
  for (const key of targets) {
    const entry = byKey.get(key);
    if (entry === void 0) {
      rejected.push({ key, reason: "no such task in the worker queue" });
    } else if (!isTerminalStatus(entry.status)) {
      rejected.push({
        key,
        reason: `not terminal (status: ${entry.status}) \u2014 only done/failed/needs-clarification rows can be acked`
      });
    } else {
      acked.push(key);
    }
  }
  const written = acked.length > 0 ? await ackStore.ack(acked) : { acked: [], rejected: [] };
  return { acked: written.acked, rejected };
}
function renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot2, key) {
  const counts = {
    pending: 0,
    running: 0,
    done: 0,
    failed: 0,
    "needs-clarification": 0
  };
  const acked = new Set(ackStore.readAll().keys());
  const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot2) === key);
  for (const e of owned) counts[e.status]++;
  const unhandled = owned.filter(
    (e) => (e.status === "failed" || e.status === "needs-clarification") && !acked.has(e.taskKey)
  );
  const idx = indexStore.findByKey(key);
  const phase = idx ? `phase=${idx.phase}` : key === SCRATCH_WORKERS_KEY ? "manual tasks" : "key not in _index.parallel";
  const badge = key === SCRATCH_WORKERS_KEY ? void 0 : formatDocsBadge(readPhaseDocs(agenticdocRoot2, key));
  const parts = [];
  if (counts.running > 0) parts.push(`${counts.running} running`);
  if (counts.pending > 0) parts.push(`${counts.pending} pending`);
  if (counts.done > 0) parts.push(`${counts.done} done`);
  if (counts.failed > 0) parts.push(`${counts.failed} failed`);
  if (counts["needs-clarification"] > 0) parts.push(`${counts["needs-clarification"]} needs-clarification`);
  if (unhandled.length > 0) parts.push(`${unhandled.length} unhandled`);
  const header = `[mw] ${key} | ${phase}${badge ? ` | docs ${badge}` : ""} | ${parts.length > 0 ? parts.join(" / ") : "no workers"}`;
  if (owned.length === 0) return [header, "  (no worker tasks)"];
  const rowLine = (e) => {
    let detail = "";
    let model = "";
    if (e.status === "running") {
      const prog = readTaskProgress(path25.dirname(e.taskPath));
      model = prog?.model ?? "";
      const hb = prog?.heartbeat;
      if (hb) {
        const ph = hb.phase === "-" ? "ph -" : `ph ${hb.phase}/${hb.phaseTotal}`;
        const up = prog?.elapsedMs !== void 0 ? ` up ${formatHeartbeatAge(prog.elapsedMs)}` : "";
        const stale = hb.ageMs > HEARTBEAT_STALE_MS ? " STALE" : "";
        detail = `${ph}${up} hb ${formatHeartbeatAge(hb.ageMs)}${stale}`;
      } else {
        detail = "(no-hb)";
      }
      const ck = prog?.checkpoint;
      if (ck) {
        detail += ` ck${Math.round(ck.elapsedS / 60)}m${ck.risk !== "low" ? ` ${ck.risk}\u26A0` : ""}`;
      }
      if (prog?.lastAction) detail += ` \xB7 ${prog.lastAction}`;
    } else if (e.status === "pending") {
      model = e.model;
    } else {
      model = readTaskProgress(path25.dirname(e.taskPath))?.model ?? "";
      detail = readTerminalDetail(path25.dirname(e.taskPath), e.status);
    }
    const badge2 = model ? ` [${model}]` : "";
    return trunc(`  ${STATUS_GLYPH[e.status]} ${e.taskKey}${badge2}${detail ? ` \u2014 ${detail}` : ""}`, WATCH_LINE_MAX);
  };
  const newestFirst = (a, b) => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
  const live = [
    ...owned.filter((e) => e.status === "running").sort(newestFirst),
    ...owned.filter((e) => e.status === "pending").sort(newestFirst)
  ];
  const history = owned.filter((e) => e.status === "done" || acked.has(e.taskKey)).sort(newestFirst);
  const lines = [header];
  for (const e of live) lines.push(rowLine(e));
  for (const e of [...unhandled].sort(newestFirst)) lines.push(rowLine(e));
  for (const e of history.slice(0, WATCH_HISTORY_MAX)) lines.push(rowLine(e));
  if (history.length > WATCH_HISTORY_MAX) lines.push(`  ... +${history.length - WATCH_HISTORY_MAX} more`);
  return lines;
}
function setWatchWidget(ctx, lines) {
  if (!ctx.hasUI) return;
  ctx.ui.setWidget(WATCH_WIDGET_KEY, lines, { placement: "belowEditor" });
}
function applyWatchWidget(ui, lines) {
  if (!ui.ctx) return;
  setWatchWidget(ui.ctx, lines);
}
function setWindowWatch(pi, watch, refresh, ctx, key, claimed) {
  watch.key = key;
  pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed });
  refresh(ctx);
}
function makeScopedDocGateNotifier(pi, watch) {
  return (key, gaps) => {
    if (!watch.key || key !== watch.key) return false;
    displaySummary(
      pi,
      `[mw] skipped dispatch for '${key}' \u2014 missing phase docs: ${gaps.join("; ")}. Generate spec/design + evidence/research notes (agentic-task workflows), or move ad-hoc work under _scratch.`
    );
    return true;
  };
}
function registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot2) {
  pi.registerCommand("pm-key", {
    description: "Manage PM keys: new / switch (take over + watch) / list",
    handler: async (args, ctx) => {
      const [sub, ...rest] = args.trim().split(/\s+/);
      const flags = rest.filter((t) => t.startsWith("--"));
      const positional = rest.filter((t) => !t.startsWith("--"));
      const keyName = positional[0] ?? "";
      const force = flags.includes("--force");
      if (sub === "list") {
        const entries = indexStore.readAll();
        if (entries.length === 0) {
          ctx.ui.notify("No keys found.", "info");
          return;
        }
        const table = entries.map((e) => `${e.key} | ${e.status} | ${e.phase} | ${e.claimId}`).join("\n");
        ctx.ui.notify(table, "info");
        return;
      }
      if (sub === "new") {
        if (!keyName) {
          ctx.ui.notify("Usage: /pm-key new <key-name>", "warning");
          return;
        }
        if (indexStore.findByKey(keyName)) {
          ctx.ui.notify(
            `Key '${keyName}' already exists \u2014 use /pm-key switch ${keyName} to take it over.`,
            "warning"
          );
          return;
        }
        const result = await takeOverKey(indexStore, keyName, false, agenticdocRoot2);
        setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
        ctx.ui.notify(`Created and claimed key: ${keyName} (${result.claimId})`, "info");
        if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
        return;
      }
      if (sub === "switch") {
        if (!keyName) {
          ctx.ui.notify("Usage: /pm-key switch <key-name> [--force]", "warning");
          return;
        }
        const target = indexStore.findByKey(keyName);
        if (!target) {
          ctx.ui.notify(`Key not found: ${keyName}`, "error");
          return;
        }
        const result = await takeOverKey(indexStore, keyName, force, agenticdocRoot2);
        if (!result.ok) {
          ctx.ui.notify(
            `Key '${keyName}' is claimed by another live window (${result.blockedBy}). Use /pm-key switch ${keyName} --force to take it over.`,
            "warning"
          );
          return;
        }
        setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
        ctx.ui.notify(`Took over key: ${keyName} (claim ${result.claimId})`, "info");
        if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
        return;
      }
      ctx.ui.notify("Usage: /pm-key new|switch|list [key-name] [--force]", "warning");
    }
  });
}
async function writeSessionSnapshot(agenticdocRoot2, key, lines) {
  const statePath = path25.join(agenticdocRoot2, key, "pm-state.md");
  const content = fs21.existsSync(statePath) ? fs21.readFileSync(statePath, "utf8") : `# PM State: ${key}

## Notes
`;
  const section = [
    `### Session Snapshot \u2014 ${(/* @__PURE__ */ new Date()).toISOString()} (${windowClaimId()})`,
    ...lines.map((l) => l ? `- ${l}` : ""),
    ""
  ].join("\n");
  const NOTES_HEADING = /^## Notes[ \t]*$/m;
  const next = NOTES_HEADING.test(content) ? content.replace(NOTES_HEADING, `## Notes

${section}`) : `${content.trimEnd()}

## Notes

${section}`;
  fs21.mkdirSync(path25.dirname(statePath), { recursive: true });
  const release = await acquireLock(`${statePath}.lock`);
  try {
    const tmpPath = `${statePath}.tmp`;
    fs21.writeFileSync(tmpPath, next, "utf8");
    fs21.renameSync(tmpPath, statePath);
  } finally {
    release();
  }
  return statePath;
}
function registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot2) {
  pi.registerCommand("pm-save", {
    description: "Save this window's working context to {watched key}/pm-state.md for restart pickup",
    handler: async (args, ctx) => {
      const note = args.trim();
      if (!watch.key) {
        ctx.ui.notify(
          "Not watching any key \u2014 /pm-key switch <key> (take over) or /mw-watch <key> (display only) first.",
          "warning"
        );
        return;
      }
      const key = watch.key;
      const row = indexStore.findByKey(key);
      const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot2) === key);
      const ORDER = ["pending", "running", "done", "failed", "needs-clarification"];
      const counts = /* @__PURE__ */ new Map();
      for (const e of owned) counts.set(e.status, (counts.get(e.status) ?? 0) + 1);
      const workerSummary = owned.length === 0 ? "no workers" : ORDER.filter((s) => counts.get(s)).map((s) => `${counts.get(s)} ${s}`).join(" / ");
      const lines = [
        `Watch: ${key} (window ${windowClaimId()})`,
        row ? `Index: status=${row.status} phase=${row.phase}${row.desc ? ` \u2014 ${row.desc}` : ""}` : "Index: (not in _index.parallel)",
        `Workers: ${workerSummary}`
      ];
      if (note) lines.push(`Note: ${note}`);
      lines.push("(agent: fill in below \u2014 \u5F53\u524D\u5DE5\u4F5C\u8109\u7EDC / \u5173\u952E\u51B3\u7B56 / \u8FDB\u884C\u4E2D / \u4E0B\u4E00\u6B65)");
      const statePath = await writeSessionSnapshot(agenticdocRoot2, key, lines);
      ctx.ui.notify(
        `Saved session snapshot to ${path25.relative(agenticdocRoot2, statePath)} \u2014 asking the agent to fill in the working context.`,
        "info"
      );
      pi.sendUserMessage(
        `[agent-team-loop] /pm-save\uFF1A\u5DF2\u5728 ${key}/pm-state.md \u7684 Notes \u533A\u5199\u5165\u4F1A\u8BDD\u5FEB\u7167\u3002\u8BF7\u7ACB\u5373\u628A\u5F53\u524D\u5BF9\u8BDD\u7684\u4E0A\u4E0B\u6587\u72B6\u6001\u8865\u5168\u5230\u8BE5\u5FEB\u7167\u5C0F\u8282\uFF1A\u5F53\u524D\u5DE5\u4F5C\u8109\u7EDC\u3001\u5173\u952E\u51B3\u7B56\u3001\u8FDB\u884C\u4E2D\u7684\u4E8B\u9879\u3001\u4E0B\u4E00\u6B65\u52A8\u4F5C\u3002\u53EA\u7F16\u8F91 ${key}/pm-state.md \u7684 Notes \u533A\uFF0C\u4E0D\u8981\u52A8 - Phase: / - Claim-Id: \u673A\u5668\u63A5\u53E3\u884C\u3002\u5199\u5B8C\u7B80\u77ED\u786E\u8BA4\u3002`
      );
    }
  });
}
function registerWatchCommand(pi, watch, refreshWatch, indexStore) {
  const USAGE2 = "Usage: /mw-watch <key> | off   (display only \u2014 /pm-key switch takes over a key)";
  pi.registerCommand("mw-watch", {
    description: "Show one key's live worker progress in a bottom widget (/mw-watch <key> | off)",
    handler: async (args, ctx) => {
      const arg = args.trim();
      if (!arg) {
        ctx.ui.notify(watch.key ? `Watching: ${watch.key}. ${USAGE2}` : `Not watching anything. ${USAGE2}`, "info");
        return;
      }
      if (arg === "off" || arg === "none") {
        watch.key = void 0;
        pi.appendEntry(WATCH_ENTRY_TYPE, { key: void 0, claimed: false });
        refreshWatch(ctx);
        ctx.ui.notify("Watch disabled \u2014 bottom widget cleared.", "info");
        return;
      }
      if (arg !== SCRATCH_WORKERS_KEY && !indexStore.findByKey(arg)) {
        ctx.ui.notify(
          `Key '${arg}' not found in _index.parallel (or use ${SCRATCH_WORKERS_KEY}). ${USAGE2}`,
          "warning"
        );
        return;
      }
      setWindowWatch(pi, watch, refreshWatch, ctx, arg, false);
      ctx.ui.notify(`Watching '${arg}' \u2014 worker progress shown below the editor.`, "info");
    }
  });
}
function registerMwTools(pi, projectDir) {
  pi.registerTool({
    name: "mw_status",
    label: "mw_status",
    description: "Check whether the multi-worker background service (mw serve) is running. Returns PID if running, or 'not running' if stopped.",
    parameters: typebox_exports.Object({}),
    execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
      const s = getMwStatus(projectDir);
      return {
        content: [
          {
            type: "text",
            text: s.running ? `mw is running (PID ${s.pid}). Workers are being dispatched and monitored.` : "mw is not running. Workers will not be dispatched. Use /mw start or ask the user to start it."
          }
        ],
        details: void 0
      };
    }
  });
}
function resolveDispatchType(cli, requested) {
  const trimmed = requested.trim();
  if (!trimmed) {
    const legacy = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
    return { ok: true, type: legacy };
  }
  if (!DISPATCHABLE_TYPES.includes(trimmed)) {
    return {
      ok: false,
      message: `Invalid type '${trimmed}'. Must be one of: ${DISPATCHABLE_TYPES.join(", ")}.`
    };
  }
  return { ok: true, type: trimmed };
}
function oneLineReason(raw) {
  return raw.replace(/\s*\r?\n\s*/g, " ").trim();
}
function dispatchPhase(agenticdocRoot2, ownerKey) {
  if (ownerKey === SCRATCH_WORKERS_KEY) return "";
  return new StateManager(agenticdocRoot2, ownerKey).read().phase ?? "";
}
function planDispatchFrontmatter(input) {
  const role = roleForTaskType(input.taskType);
  const configured = readRoleModel(input.cwd, role) ?? "";
  const requested = input.model.trim();
  const reason = oneLineReason(input.modelReason);
  const typeLines = input.phase !== void 0 && input.phase.length > 0 ? `type: ${input.taskType}
phase: ${input.phase}
` : `type: ${input.taskType}
`;
  const effective = requested || configured;
  if (effective) {
    const validation = validateModelValue(input.registry, input.cli, input.provider, effective);
    if (!validation.ok) return { ok: false, message: validation.message };
  }
  if (!requested) {
    return {
      ok: true,
      frontmatter: typeLines,
      echo: configured ? `model: dispatch.yml ${role}=${configured}` : `model: route default (no dispatch.yml ${role} default)`
    };
  }
  if (configured && requested === configured) {
    return {
      ok: true,
      frontmatter: typeLines,
      echo: `model: dispatch.yml ${role}=${configured} (requested value matches the configured default; not pinned)`
    };
  }
  if (configured && !reason) {
    return {
      ok: false,
      message: `Model override for role '${role}' needs model_reason: dispatch.yml ${role}=${configured}, requested=${requested}. Omit the model to use the configured default, or re-dispatch with model_reason explaining the deviation.`
    };
  }
  const lines = input.phase !== void 0 && input.phase.length > 0 ? [`type: ${input.taskType}`, `phase: ${input.phase}`] : [`type: ${input.taskType}`];
  if (requested) lines.push(`model: ${requested}`);
  if (reason) lines.push(`model-reason: ${reason}`);
  return {
    ok: true,
    frontmatter: `${lines.join("\n")}
`,
    echo: configured ? `model override: role default ${role}=${configured} -> ${requested} (reason: ${reason})` : `model: ${requested} (no dispatch.yml ${role} default)`
  };
}
function registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot2, watch, projectDir = path25.dirname(agenticdocRoot2)) {
  pi.registerTool({
    name: "dispatch_worker",
    label: "dispatch_worker",
    description: "Dispatch a task to a background worker agent. Creates .agenticdoc/<task_key>/task.md and queues it for execution by the mw worker service. Returns the task key on success.",
    parameters: typebox_exports.Object({
      task_key: typebox_exports.String({
        description: "Unique kebab-case key for this task (e.g. 'fix-login-bug', 'add-auth-endpoint'). Must be unique across tasks in this project."
      }),
      description: typebox_exports.String({
        description: "Full task description and instructions for the worker agent."
      }),
      cli: typebox_exports.Optional(
        typebox_exports.String({
          description: "Worker CLI: 'pi' (default for all task types incl. review/research), 'claude' (explicit override \u2014 requires claude credentials, fails per-task when missing), 'codex' (codex tasks)."
        })
      ),
      model: typebox_exports.Optional(
        typebox_exports.String({
          description: "Optional model override for this worker (e.g. 'timi/gpt-5.6-sol'). Deviating from the configured .mw/dispatch.yml role default requires model_reason; a value equal to that default is not pinned (the config stays the source of truth)."
        })
      ),
      model_reason: typebox_exports.Optional(
        typebox_exports.String({
          description: "Why this task deviates from the .mw/dispatch.yml role default. Required when model is set and the role has a configured default with a different value; recorded in task.md as model-reason."
        })
      ),
      type: typebox_exports.Optional(
        typebox_exports.String({
          description: "Task type: 'coding' | 'review' | 'research'. Selects the dispatch.yml role (and the worker tool allowlist). Default: derived from cli (pi -> coding, claude -> review, codex -> codex)."
        })
      ),
      key: typebox_exports.Optional(
        typebox_exports.String({
          description: "AgenticTask key owning this worker task. Default: this window's claimed key (the one it watches and holds in _index.parallel), else the active key when no other live window holds it, else _scratch."
        })
      )
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
      const {
        task_key,
        description,
        cli = "pi",
        model,
        model_reason,
        type,
        key
      } = params;
      const ragCheck = validateRagEnabled(projectDir);
      if (!ragCheck.ok) {
        return { content: [{ type: "text", text: ragCheck.message }], details: void 0 };
      }
      const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, key, agenticdocRoot2);
      const validCli = ["pi", "claude", "codex"];
      if (!validCli.includes(cli)) {
        return {
          content: [{ type: "text", text: `Invalid cli '${cli}'. Must be one of: ${validCli.join(", ")}.` }],
          details: void 0
        };
      }
      const typeResolution = resolveDispatchType(cli, type ?? "");
      if (!typeResolution.ok) {
        return { content: [{ type: "text", text: typeResolution.message }], details: void 0 };
      }
      const provider = cli === "pi" ? "timi" : "";
      const docGaps = dispatchDocGaps(agenticdocRoot2, ownerKey);
      if (docGaps.length > 0) {
        return {
          content: [
            {
              type: "text",
              text: `Worker dispatch blocked: key '${ownerKey}' is missing phase documentation.
${docGaps.map((g) => `- ${g}`).join("\n")}
${DOC_GATE_HINT}`
            }
          ],
          details: void 0
        };
      }
      const taskDir = workerTaskDir(agenticdocRoot2, ownerKey, task_key);
      if (fs21.existsSync(taskDir)) {
        return {
          content: [
            {
              type: "text",
              text: `Task '${task_key}' already exists at ${taskDir}. Choose a different task_key or check existing tasks with list_tasks.`
            }
          ],
          details: void 0
        };
      }
      const typeField = typeResolution.type;
      const modelPlan = planDispatchFrontmatter({
        cwd: projectDir,
        cli,
        provider,
        taskType: typeField,
        phase: dispatchPhase(agenticdocRoot2, ownerKey),
        model: model ?? "",
        modelReason: model_reason ?? "",
        registry: _context?.modelRegistry
      });
      if (!modelPlan.ok) {
        return { content: [{ type: "text", text: modelPlan.message }], details: void 0 };
      }
      fs21.mkdirSync(taskDir, { recursive: true });
      const taskMdPath = path25.join(taskDir, "task.md");
      fs21.writeFileSync(taskMdPath, `${modelPlan.frontmatter}
${description}
`, "utf8");
      await dispatchTask(
        { taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath },
        workerStore
      );
      return {
        content: [
          {
            type: "text",
            text: `Dispatched worker '${task_key}' (type: ${typeField}, role: ${roleForTaskType(typeField)}, ${modelPlan.echo}) under key '${ownerKey}'. Task file: ${taskMdPath}. Check mw_status to confirm the service is running.`
          }
        ],
        details: void 0
      };
    }
  });
  pi.registerTool({
    name: "ack_worker_result",
    label: "ack_worker_result",
    description: "Acknowledge a worker's terminal result (done/failed/needs-clarification) after absorbing it: the row moves out of the watch widget's unhandled section into folded history. task_key acks one task; 'all' acks every unacked terminal task.",
    promptGuidelines: [
      "After absorbing a terminal worker result (the readback body / output.md), call ack_worker_result with its task_key \u2014 or 'all' after a batch \u2014 so the widget's unhandled section clears; unacked failed/needs-clarification rows stay listed until acked."
    ],
    parameters: typebox_exports.Object({
      task_key: typebox_exports.String({ description: "Worker task key to ack, or 'all' for every unacked terminal task." })
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
      const { task_key } = params;
      const target = task_key.trim();
      if (!target) {
        return { content: [{ type: "text", text: "task_key is required (or 'all')." }], details: void 0 };
      }
      const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target]);
      const parts = [];
      if (result.acked.length > 0) parts.push(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}.`);
      for (const r of result.rejected) parts.push(`NOT acked: ${r.key} \u2014 ${r.reason}.`);
      if (parts.length === 0) parts.push("No unacked terminal tasks.");
      return { content: [{ type: "text", text: parts.join("\n") }], details: void 0 };
    }
  });
  pi.registerTool({
    name: "list_tasks",
    label: "list_tasks",
    description: "List all worker tasks in this project with their current status (pending / running / done / failed / needs-clarification). Acked terminal tasks are badged 'acked'.",
    parameters: typebox_exports.Object({}),
    execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
      const entries = workerStore.readAll();
      if (entries.length === 0) {
        return { content: [{ type: "text", text: "No tasks found." }], details: void 0 };
      }
      const acked = new Set(ackStore.readAll().keys());
      const lines = entries.map((e) => {
        const base = `${e.taskKey} | ${e.status} | ${e.cli}${e.model ? ` | model: ${e.model}` : ""}`;
        return acked.has(e.taskKey) ? `${base} | acked` : base;
      });
      return { content: [{ type: "text", text: lines.join("\n") }], details: void 0 };
    }
  });
}
function registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot2) {
  pi.registerTool({
    name: "switch_key",
    label: "switch_key",
    description: "Take over (claim + watch) an AgenticTask key in this window: marks it active in _index.parallel with this window's claim (host:pid) and shows its live worker progress in the bottom widget. Call it when the user asks to take over or switch to a key, or when you are about to execute a key's tasks in this window. Writing .agenticdoc/{key}/spec.md, design.md, or plan.md switches automatically \u2014 no call needed. If another live window holds the key's claim, the call fails unless force is true; tell the user and let them decide.",
    promptGuidelines: [
      "Before doing real work on an AgenticTask key (executing its tasks), make sure this window has taken it over via switch_key; if the user has not asked for that key, ask them first whether to switch."
    ],
    parameters: typebox_exports.Object({
      key: typebox_exports.String({ description: "The AgenticTask key to take over." }),
      force: typebox_exports.Optional(
        typebox_exports.Boolean({
          description: "Steal the claim even if another live window holds it. Only with the user's explicit confirmation."
        })
      )
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => {
      const { key, force = false } = params;
      const trimmed = key.trim();
      if (!trimmed) {
        return { content: [{ type: "text", text: "key is required." }], details: void 0 };
      }
      const result = await takeOverKey(indexStore, trimmed, force, agenticdocRoot2);
      if (!result.ok) {
        return {
          content: [
            {
              type: "text",
              text: `Key '${trimmed}' is claimed by another live window (${result.blockedBy}). The takeover was NOT performed. Tell the user; they can decide on a forced takeover (force=true).`
            }
          ],
          details: void 0
        };
      }
      watch.key = trimmed;
      pi.appendEntry(WATCH_ENTRY_TYPE, { key: trimmed, claimed: true });
      refreshWatch(ctx);
      const auditNote = result.audit.length > 0 ? `

PHASE-CHAIN AUDIT WARNINGS for this key (fix before continuing; phase changes go through advance_phase.py only):
${result.audit.join("\n")}` : "";
      return {
        content: [
          {
            type: "text",
            text: `Took over key '${trimmed}' (claim ${result.claimId})${result.created ? " \u2014 new key registered in _index.parallel" : ""}. This window now watches it; the bottom widget shows its live progress. Previously active keys were marked idle.` + auditNote
          }
        ],
        details: void 0
      };
    }
  });
}
function registerAdvancePhaseTool(pi, projectDir) {
  const ladder = PHASE_ORDER.map((p) => p.toLowerCase());
  pi.registerTool({
    name: "advance_phase",
    label: "advance_phase",
    description: "Advance an AgenticTask key to the target phase by running the framework gate script (advance_phase.py): checks the phase-gate evidence (spec/design/plan/tasks/execute/done prerequisites), updates pm-state.md, and syncs _index.parallel. Runs the Python script directly without a shell \u2014 prefer this over `python .../advance_phase.py` via the bash tool. This is the only sanctioned way to change a key's phase; hand-editing pm-state.md's '- Phase:' line is blocked.",
    promptGuidelines: [
      "Change phases only through this tool (or the equivalent python script when the shell works); when the result reports GATE BLOCKED, fix the listed evidence gaps before retrying."
    ],
    parameters: typebox_exports.Object({
      key: typebox_exports.String({ description: "AgenticTask key to advance (not _scratch)." }),
      target_phase: typebox_exports.String({
        description: "Target phase (any case): spec | design | plan | tasks | execute | verify | done."
      }),
      summary: typebox_exports.Optional(
        typebox_exports.String({
          description: "Required when target_phase is done: one-line closing summary (what was added/changed + impact surface) recorded in _project_log.md as the cross-key summary row."
        })
      ),
      supersedes: typebox_exports.Optional(
        typebox_exports.String({
          description: "Key this one supersedes, recorded in _project_log.md when advancing to done."
        })
      )
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
      const { key, target_phase, summary, supersedes } = params;
      const trimmedKey = key.trim();
      const target = target_phase.trim().toLowerCase();
      if (!trimmedKey || !target) {
        return { content: [{ type: "text", text: "key and target_phase are required." }], details: void 0 };
      }
      if (trimmedKey.startsWith("_") || trimmedKey.startsWith(".")) {
        return {
          content: [
            {
              type: "text",
              text: `Key '${trimmedKey}' has a reserved prefix and is not a phase-tracked AgenticTask key.`
            }
          ],
          details: void 0
        };
      }
      if (!ladder.includes(target)) {
        return {
          content: [
            { type: "text", text: `Unknown phase '${target_phase.trim()}'. Valid: ${ladder.join(" | ")}.` }
          ],
          details: void 0
        };
      }
      if (target === "done" && !(summary ?? "").trim()) {
        return {
          content: [
            {
              type: "text",
              text: "Advancing to done requires a non-empty summary \u2014 one line on what was added/changed and the impact surface (written to _project_log.md as the cross-key summary row)."
            }
          ],
          details: void 0
        };
      }
      const args = [trimmedKey, target];
      if (summary) args.push("--summary", summary);
      if (supersedes) args.push("--supersedes", supersedes);
      const result = runAgenticScript(projectDir, "advance_phase.py", args);
      return { content: [{ type: "text", text: result.output }], details: void 0 };
    }
  });
}
function registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot2, watch, projectDir = path25.dirname(agenticdocRoot2)) {
  const USAGE2 = "Usage: /worker <claude|codex|pi> [--type coding|review|research] [--model <id>] [--reason <text>] [--key <name>] <task description>";
  pi.registerCommand("worker", {
    description: "Spawn a worker: /worker <claude|codex|pi> [--type <t>] [--model <id>] [--reason <text>] <task description>",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/);
      const cli = (parts[0] ?? "").toLowerCase();
      let idx = 1;
      let model = "";
      let modelReason = "";
      let typeArg = "";
      let keyArg = "";
      while (["--model", "--type", "--reason", "--key"].includes(parts[idx] ?? "")) {
        const flag = parts[idx];
        const value = parts[idx + 1] ?? "";
        idx += 2;
        if (!value) {
          ctx.ui.notify(USAGE2, "warning");
          return;
        }
        if (flag === "--model") model = value;
        else if (flag === "--type") typeArg = value;
        else if (flag === "--reason") modelReason = value;
        else keyArg = value;
      }
      const description = parts.slice(idx).join(" ");
      const validCli = ["claude", "codex", "pi"];
      if (!validCli.includes(cli)) {
        ctx.ui.notify(USAGE2, "warning");
        return;
      }
      if (!description) {
        ctx.ui.notify("Task description is required.", "warning");
        return;
      }
      const typeResolution = resolveDispatchType(cli, typeArg);
      if (!typeResolution.ok) {
        ctx.ui.notify(typeResolution.message, "warning");
        return;
      }
      const typeField = typeResolution.type;
      const provider = cli === "pi" ? "timi" : "";
      const ragCheck = validateRagEnabled(projectDir);
      if (!ragCheck.ok) {
        ctx.ui.notify(ragCheck.message, "warning");
        return;
      }
      const taskKey = `manual-${Date.now()}`;
      const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, keyArg, agenticdocRoot2);
      const docGaps = dispatchDocGaps(agenticdocRoot2, ownerKey);
      if (docGaps.length > 0) {
        ctx.ui.notify(
          `Worker dispatch blocked ('${ownerKey}'): ${docGaps.join("; ")}. Generate the phase docs first or dispatch under _scratch.`,
          "warning"
        );
        return;
      }
      const modelPlan = planDispatchFrontmatter({
        cwd: projectDir,
        cli,
        provider,
        taskType: typeField,
        phase: dispatchPhase(agenticdocRoot2, ownerKey),
        model,
        modelReason,
        registry: ctx.modelRegistry
      });
      if (!modelPlan.ok) {
        ctx.ui.notify(modelPlan.message, "warning");
        return;
      }
      const taskDir = workerTaskDir(agenticdocRoot2, ownerKey, taskKey);
      fs21.mkdirSync(taskDir, { recursive: true });
      const taskMdPath = path25.join(taskDir, "task.md");
      fs21.writeFileSync(taskMdPath, `${modelPlan.frontmatter}
${description}
`, "utf8");
      await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);
      ctx.ui.notify(
        `Dispatched ${cli} worker (${taskKey}) under key '${ownerKey}' [type: ${typeField}, role: ${roleForTaskType(typeField)}, ${modelPlan.echo}].`,
        "info"
      );
    }
  });
}
function formatRagDoctorLine(rag) {
  if (rag.error) return `rag: ERROR - ${rag.error}`;
  const enabled = rag.enabled ?? [];
  const skillStatus = rag.skill?.status ?? "unknown";
  if (enabled.length === 0) return `rag: not enabled (skill ${skillStatus})`;
  const probe = rag.probe ?? {};
  const state = Object.keys(probe).sort().map((name) => `${name}=${probe[name]?.reachable ? "reachable" : "unreachable"}`).join(", ");
  const fingerprint = (rag.fingerprint ?? "").slice(0, 12);
  const rawRequired = rag.required_missing ?? 0;
  const requiredMissing = Number.isFinite(rawRequired) ? Math.trunc(rawRequired) : 0;
  const required = requiredMissing ? `; required_missing=${requiredMissing}` : "";
  return `rag: enabled=${enabled.join(", ")}; probe=${state}; fingerprint=${fingerprint}; skill=${skillStatus}${required}`;
}
function shouldShowRagDoctorRow(rag) {
  return rag !== void 0 && (rag.exists === true || (rag.enabled?.length ?? 0) > 0);
}
function formatDoctorReport(report, fix) {
  const lines = [];
  const svc = report.service;
  lines.push(svc?.running ? `\u670D\u52A1: \u8FD0\u884C\u4E2D (PID ${svc.pid ?? "?"})` : "\u670D\u52A1: \u672A\u8FD0\u884C");
  const proxyParts = (report.proxy ?? []).map(
    (p) => `${p.route ?? "?"}/${p.port ?? "?"} ${p.listening ? "\u76D1\u542C\u4E2D" : "\u672A\u76D1\u542C"}`
  );
  if (proxyParts.length > 0) lines.push(`\u4EE3\u7406\u7AEF\u53E3: ${proxyParts.join("; ")}`);
  const orphan = report.orphan_proxy;
  if (orphan?.detected) {
    const ports = (orphan.ports ?? []).map((p) => `${p.port} (PID ${(p.owner_pids ?? []).join(",") || "?"})`);
    lines.push(`\u5B64\u513F\u4EE3\u7406: ${ports.join("; ")}\uFF08mw \u672A\u8FD0\u884C\u4F46\u7AEF\u53E3\u88AB\u5360\uFF0C\u53EF\u542F\u52A8 mw \u63A5\u7BA1\u6216\u5904\u7F6E\u5360\u7528\u8FDB\u7A0B\uFF09`);
  }
  const log = report.launcher_log;
  if (log?.exists) {
    lines.push(`launcher \u65E5\u5FD7: ${log.error_count ?? 0} \u4E2A\u9519\u8BEF\u884C${log.fatal ? "\uFF08\u542B FATAL\uFF09" : ""}`);
  } else {
    lines.push("launcher \u65E5\u5FD7: \u65E0\u65E5\u5FD7\u6587\u4EF6");
  }
  const queue = report.queue;
  lines.push(
    `\u961F\u5217: ${queue?.non_terminal?.length ?? 0} \u4E2A\u8FDB\u884C\u4E2D\u4EFB\u52A1\uFF0C${queue?.stale_count ?? 0} \u4E2A stale\uFF0C${queue?.archived_total ?? 0} \u6761\u5DF2\u5F52\u6863`
  );
  const liveness = report.worker_liveness ?? [];
  if (liveness.length > 0) {
    const alive = liveness.filter((v) => v.verdict === "alive").length;
    const stale = liveness.filter((v) => v.verdict === "stale").map((v) => v.task_key ?? "?");
    const noHb = liveness.filter((v) => v.verdict === "no-heartbeat").length;
    const parts = [`\u5B58\u6D3B ${alive}`];
    if (stale.length > 0) parts.push(`\u7591\u4F3C\u6302\u8D77: ${stale.join(", ")}`);
    if (noHb > 0) parts.push(`\u65E0\u5FC3\u8DF3 ${noHb}`);
    lines.push(`worker \u6D3B\u6027: ${parts.join("; ")}`);
  }
  const credParts = (report.credentials?.routes ?? []).map(
    (r) => `${r.route ?? "?"} ${r.available ? "\u53EF\u7528" : "\u7F3A\u51ED\u8BC1"}`
  );
  if (credParts.length > 0) lines.push(`\u8DEF\u7531\u51ED\u8BC1: ${credParts.join("; ")}\uFF08\u4EE5 mw \u8FDB\u7A0B env \u4E3A\u51C6\uFF09`);
  const bundle = report.bundle;
  if (bundle?.available) {
    lines.push(bundle.stale ? "\u6269\u5C55 bundle: \u6E90\u7801\u8F83\u65B0\uFF0C\u5EFA\u8BAE /mw build \u91CD\u5EFA" : "\u6269\u5C55 bundle: \u6700\u65B0");
  }
  const piShell = report.pi_shell;
  if (piShell?.status === "ok") {
    lines.push(`pi shell: ${piShell.shell_path ?? "?"}`);
  } else if (piShell?.status && piShell.status !== "not-applicable") {
    lines.push(`pi shell: ${piShell.status} \u2014 ${piShell.detail ?? ""}`);
  }
  const dispatch = report.dispatch;
  if (dispatch?.exists) {
    if (dispatch.error) {
      lines.push(`\u6D3E\u53D1\u6A21\u578B: \u914D\u7F6E\u9519\u8BEF \u2014 ${dispatch.error}`);
    } else {
      const roles = Object.entries(dispatch.models ?? {}).map(([role, value]) => `${role}=${value}`).join("; ");
      const window = dispatch.window_model || "\uFF08\u672A\u8BB0\u5F55\uFF09";
      lines.push(`\u6D3E\u53D1\u6A21\u578B: ${roles || "\u672A\u8BBE\u89D2\u8272"}; \u7A97\u53E3\u6A21\u578B ${window}`);
    }
  }
  if (shouldShowRagDoctorRow(report.rag)) lines.push(formatRagDoctorLine(report.rag));
  if (fix) {
    const applied = report.fix?.applied;
    lines.push(Array.isArray(applied) && applied.length > 0 ? `\u5DF2\u81EA\u52A8\u4FEE\u590D: ${applied.join("; ")}` : "\u65E0\u53EF\u81EA\u52A8\u4FEE\u590D\u9879");
  }
  const summary = report.summary;
  if (summary?.healthy) {
    lines.push("\u6574\u4F53: \u5065\u5EB7");
  } else {
    const issues = Array.isArray(summary?.issues) ? summary?.issues : [];
    lines.push(issues.length > 0 ? `\u6574\u4F53: ${issues.length} \u4E2A\u95EE\u9898 \u2014 ${issues.join("; ")}` : "\u6574\u4F53: \u672A\u77E5");
  }
  const suggestions = Array.isArray(summary?.suggestions) ? summary?.suggestions : [];
  for (const s of suggestions) lines.push(`\u5EFA\u8BAE: ${s}`);
  return lines.join("\n");
}
function splitCommandLine(line) {
  const out = [];
  let cur = "";
  let inQuote = false;
  let has = false;
  for (const ch of line) {
    if (ch === '"') {
      inQuote = !inQuote;
      has = true;
    } else if (!inQuote && /\s/.test(ch)) {
      if (has) {
        out.push(cur);
        cur = "";
        has = false;
      }
    } else {
      cur += ch;
      has = true;
    }
  }
  if (has) out.push(cur);
  return out;
}
function parseTargetSetFlags(parts) {
  const flags = { game: "" };
  for (let i = 0; i < parts.length; i++) {
    const m = /^--(game|engine|vcs|uproject)$/.exec(parts[i]);
    if (!m) continue;
    const value = parts[i + 1];
    if (value === void 0 || value.startsWith("--")) return null;
    flags[m[1]] = value;
    i++;
  }
  if (!flags.game) return null;
  return flags;
}
async function runMwTargetCommand(ctx, projectDir, argsText, runner = targetMw) {
  const parts = splitCommandLine(argsText);
  const action = parts[0] ?? "";
  if (action === "show" || action === "clear" || action === "on" || action === "off") {
    const r = runner(projectDir, [action]);
    ctx.ui.notify(
      r.ok ? r.output || `mw target ${action}: ok` : `mw target ${action} failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  if (action === "set") {
    const flags = parseTargetSetFlags(parts.slice(1));
    if (!flags) {
      ctx.ui.notify(
        "Usage: /mw target set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] \u2014 quote paths containing spaces",
        "warning"
      );
      return;
    }
    const args = ["set", `--game=${flags.game}`];
    if (flags.engine !== void 0) args.push(`--engine=${flags.engine}`);
    if (flags.vcs !== void 0) args.push(`--vcs=${flags.vcs}`);
    if (flags.uproject !== void 0) args.push(`--uproject=${flags.uproject}`);
    const r = runner(projectDir, args);
    ctx.ui.notify(
      r.ok ? `${r.output}
Dual mode takes effect on the next worker spawn (no serve restart needed).` : `mw target set failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  ctx.ui.notify(
    "Usage: /mw target show | set --game <dir> [--engine <dir>] [--vcs git|p4|none] [--uproject <file>] | clear | on | off",
    "warning"
  );
}
function parsePartitionSetFlags(parts) {
  const flags = { parent: "", roots: [] };
  for (let i = 0; i < parts.length; i++) {
    const m = /^(--parent|--partition|--vcs|--root)$/.exec(parts[i]);
    if (!m) continue;
    const value = parts[i + 1];
    if (value === void 0 || value.startsWith("--")) return null;
    if (m[1] === "--root") {
      flags.roots.push(value);
    } else {
      flags[m[1].slice(2)] = value;
    }
    i++;
  }
  if (!flags.parent) return null;
  return flags;
}
async function runMwPartitionCommand(ctx, projectDir, argsText, runner = partitionMw) {
  const parts = splitCommandLine(argsText);
  const action = parts[0] ?? "";
  if (action === "show" || action === "clear" || action === "on" || action === "off") {
    const r = runner(projectDir, [action]);
    ctx.ui.notify(
      r.ok ? r.output || `mw partition ${action}: ok` : `mw partition ${action} failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  if (action === "set") {
    const flags = parsePartitionSetFlags(parts.slice(1));
    if (!flags) {
      ctx.ui.notify(
        "Usage: /mw partition set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] \u2014 quote paths containing spaces",
        "warning"
      );
      return;
    }
    const args = ["set", `--parent=${flags.parent}`];
    if (flags.partition !== void 0) args.push(`--partition=${flags.partition}`);
    if (flags.vcs !== void 0) args.push(`--vcs=${flags.vcs}`);
    for (const root of flags.roots) args.push(`--root=${root}`);
    const r = runner(projectDir, args);
    ctx.ui.notify(
      r.ok ? `${r.output}
Partition mode takes effect on the next worker spawn (no serve restart needed).` : `mw partition set failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  ctx.ui.notify(
    "Usage: /mw partition show | set --parent <dir> [--partition <dir>] [--root name=<dir> ...] [--vcs git|p4|none] | clear | on | off",
    "warning"
  );
}
async function runMwModelCommand(ctx, projectDir, argsText, runner = modelMw) {
  const parts = splitCommandLine(argsText);
  const action = parts[0] ?? "show";
  if (action === "show") {
    const r = runner(projectDir, ["show"]);
    ctx.ui.notify(
      r.ok ? r.output || "mw model show: ok" : `mw model show failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  if (action === "set") {
    const role = parts[1];
    const value = parts[2];
    if (!role || !value || parts.length > 3) {
      ctx.ui.notify(
        "Usage: /mw model set <role> <prefix/model> \u2014 roles: main, coding, review, research (e.g. /mw model set review timi/gpt-5.6-sol)",
        "warning"
      );
      return;
    }
    const validation = validateModelValue(ctx.modelRegistry, "pi", "", value);
    if (!validation.ok) {
      ctx.ui.notify(validation.message, "error");
      return;
    }
    const r = runner(projectDir, ["set", role, value]);
    ctx.ui.notify(
      r.ok ? `${r.output}
Worker roles apply on the next spawn (no serve restart); main applies at the next window start.` : `mw model set failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  if (action === "clear") {
    const role = parts[1];
    if (!role || parts.length > 2) {
      ctx.ui.notify("Usage: /mw model clear <role|all>", "warning");
      return;
    }
    const r = runner(projectDir, ["clear", role]);
    ctx.ui.notify(
      r.ok ? r.output || "mw model clear: ok" : `mw model clear failed: ${r.error}`,
      r.ok ? "info" : "error"
    );
    return;
  }
  ctx.ui.notify("Usage: /mw model show | set <role> <prefix/model> | clear <role|all>", "warning");
}
var MW_COMMAND_DESCRIPTION = "Control mw: build / init / start / stop / restart / status / doctor / update / target / partition / model / rag / ack";
var RAG_OUTPUT_MAX_LINES = 30;
var RAG_FULL_OUTPUT_HINT = "\u5B8C\u6574\u8F93\u51FA\uFF1Apython mw.py rag <sub> --project <dir>";
function parseRagArgs(raw) {
  const usage = `Usage: /mw rag <sub> [args...] \u2014 sub: ${RAG_SUBCOMMANDS.join(
    " | "
  )}. Arguments are forwarded to mw.py rag verbatim.`;
  const parts = splitCommandLine(raw);
  const sub = parts[0] ?? "";
  if (!RAG_SUBCOMMANDS.includes(sub)) return { usage };
  return { sub, rest: parts.slice(1) };
}
function formatRagOutput(output, code) {
  const level = code === 0 ? "info" : code === 1 ? "warning" : "error";
  const text = output.replace(/\r\n/g, "\n").trim();
  if (text === "") return { text: code === 0 ? "mw rag: ok" : `mw rag exited with code ${code}`, level };
  const lines = text.split("\n");
  if (lines.length <= RAG_OUTPUT_MAX_LINES) return { text, level };
  return { text: `${lines.slice(0, RAG_OUTPUT_MAX_LINES).join("\n")}
\u2026 ${RAG_FULL_OUTPUT_HINT}`, level };
}
async function runMwRagCommand(ctx, projectDir, raw, runner = ragMw) {
  const parsed = parseRagArgs(raw);
  if ("usage" in parsed) {
    ctx.ui.notify(parsed.usage, "warning");
    return;
  }
  const result = runner(projectDir, [parsed.sub, ...parsed.rest]);
  const formatted = formatRagOutput(result.output, result.code);
  ctx.ui.notify(formatted.text, formatted.level);
}
function registerMwCommands(pi, projectDir, workerStore, ackStore) {
  pi.registerCommand("mw", {
    description: MW_COMMAND_DESCRIPTION,
    handler: async (_args, ctx) => {
      const trimmed = _args.trim();
      const sub = trimmed.split(/\s+/)[0] ?? "status";
      if (sub === "build") {
        ctx.ui.notify("Rebuilding extension bundle (bash-free)\u2026", "info");
        const r = buildMw();
        if (r.ok) {
          ctx.ui.notify(`mw build OK \u2014 reinstalled globally. Restart pi windows to load it.
${r.output}`, "info");
        } else {
          ctx.ui.notify(`mw build failed: ${r.error}`, "error");
        }
        return;
      }
      if (sub === "init") {
        const result = initMw(projectDir);
        if (result.ok) {
          ctx.ui.notify("mw init complete \u2014 .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
        } else {
          ctx.ui.notify(result.error, "error");
        }
        return;
      }
      if (sub === "doctor") {
        const fix = _args.trim().split(/\s+/)[1]?.toLowerCase() === "fix";
        const r = doctorMw(projectDir, fix);
        if (r.ok) {
          ctx.ui.notify(formatDoctorReport(r.report, fix), "info");
        } else {
          ctx.ui.notify(`mw doctor \u6267\u884C\u5931\u8D25: ${r.error}`, "error");
        }
        return;
      }
      if (sub === "update") {
        const apply = _args.trim().split(/\s+/)[1]?.toLowerCase() === "--apply";
        ctx.ui.notify(
          apply ? "mw update-env --apply running (bundle/dist rebuild + reinstall can take a minute)\u2026" : "mw update-env checking anchors\u2026",
          "info"
        );
        const r = updateEnvMw(projectDir, apply);
        ctx.ui.notify(r.ok ? r.output : `mw update-env \u6267\u884C\u5931\u8D25: ${r.error}`, r.ok ? "info" : "error");
        return;
      }
      if (sub === "status") {
        const s = getMwStatus(projectDir);
        if (!s.running) {
          ctx.ui.notify("mw not running", "info");
          return;
        }
        const stale = serveStaleness(projectDir);
        ctx.ui.notify(
          stale?.stale ? `mw running (PID ${s.pid}) \u2014 STALE CODE (${stale.detail}). Run /mw restart.` : `mw running (PID ${s.pid})`,
          stale?.stale ? "warning" : "info"
        );
        return;
      }
      if (sub === "start") {
        const s = getMwStatus(projectDir);
        if (s.running) {
          ctx.ui.notify(`mw already running (PID ${s.pid})`, "info");
          return;
        }
        const ok = startMw(projectDir);
        ctx.ui.notify(
          ok ? "mw starting in background\u2026" : "Could not find mw.py \u2014 set MW_PY env var.",
          ok ? "info" : "error"
        );
        return;
      }
      if (sub === "stop") {
        const s = getMwStatus(projectDir);
        if (!s.running) {
          ctx.ui.notify("mw is not running", "info");
          return;
        }
        stopMw(projectDir);
        ctx.ui.notify("mw stop signal sent", "info");
        return;
      }
      if (sub === "restart") {
        ctx.ui.notify("mw restarting (graceful stop, then start)...", "info");
        const r = await restartMw(projectDir);
        if (r === "restarted") {
          const s = getMwStatus(projectDir);
          ctx.ui.notify(
            `mw restarted (PID ${s.pid ?? "?"}) \u2014 in-flight workers are adopted by the new launcher's orphan reconcile.`,
            "info"
          );
        } else if (r === "stop-failed") {
          ctx.ui.notify("mw restart failed: serve did not exit in time \u2014 run /mw doctor.", "error");
        } else {
          ctx.ui.notify("mw restart failed: serve did not come up \u2014 run /mw doctor.", "error");
        }
        return;
      }
      if (sub === "target") {
        await runMwTargetCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
        return;
      }
      if (sub === "partition") {
        await runMwPartitionCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
        return;
      }
      if (sub === "model") {
        await runMwModelCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
        return;
      }
      if (sub === "rag") {
        await runMwRagCommand(ctx, projectDir, trimmed.slice(sub.length).trim());
        return;
      }
      if (sub === "ack") {
        const target = _args.trim().split(/\s+/)[1] ?? "";
        if (!target) {
          ctx.ui.notify("Usage: /mw ack <task-key> | all", "warning");
          return;
        }
        const result = await ackTasks(workerStore, ackStore, target === "all" ? "all" : [target]);
        if (result.acked.length > 0) {
          ctx.ui.notify(`Acked ${result.acked.length} task(s): ${result.acked.join(", ")}`, "info");
        }
        for (const r of result.rejected) ctx.ui.notify(`Not acked: ${r.key} \u2014 ${r.reason}`, "warning");
        if (result.acked.length === 0 && result.rejected.length === 0) {
          ctx.ui.notify("No unacked terminal tasks.", "info");
        }
        return;
      }
      ctx.ui.notify(
        "Usage: /mw build|init|start|stop|status|doctor [fix] | update [--apply] | target show|set|clear|on|off | partition show|set|clear|on|off | model show|set|clear | rag <sub> | ack <task-key>|all",
        "warning"
      );
    }
  });
}

// packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts
import * as fs22 from "node:fs";
var GATE_FIELD_LINE_RE = /^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?[ \t]*$/;
var ANSWER_FIELDS = ["status", "answered_at", "answered_by", "note"];
var PLAIN_SCALAR_RE = /^[A-Za-z0-9][A-Za-z0-9_./:+@()-]*$/;
var AMBIGUOUS_SCALARS = /* @__PURE__ */ new Set([
  "",
  "-",
  "~",
  "null",
  "Null",
  "NULL",
  "true",
  "True",
  "TRUE",
  "false",
  "False",
  "FALSE",
  "yes",
  "Yes",
  "YES",
  "no",
  "No",
  "NO",
  "on",
  "On",
  "off",
  "Off"
]);
function renderScalar(value) {
  if (!AMBIGUOUS_SCALARS.has(value) && PLAIN_SCALAR_RE.test(value)) return value;
  return `'${value.replaceAll("'", "''")}'`;
}
function isoNowSeconds() {
  return (/* @__PURE__ */ new Date()).toISOString().replace(/\.\d{3}Z$/, "Z");
}
function rewriteAnswerFields(content, replacements, gateFile) {
  const lines = content.split("\n");
  if (lines.length === 0 || lines[0].trim() !== "---") {
    return { ok: false, error: `${gateFile}: frontmatter must open with a '---' line` };
  }
  let end = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === "---") {
      end = i;
      break;
    }
  }
  if (end < 0) return { ok: false, error: `${gateFile}: frontmatter never closes with a '---' line` };
  const rewritten = /* @__PURE__ */ new Set();
  for (let i = 1; i < end; i++) {
    const raw = lines[i];
    const probe = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    const m = GATE_FIELD_LINE_RE.exec(probe);
    if (m === null) continue;
    const name = m[1] ?? "";
    if (!ANSWER_FIELDS.includes(name) || rewritten.has(name)) continue;
    const value = replacements.get(name) ?? "";
    lines[i] = (value === "" ? `${name}:` : `${name}: ${value}`) + (raw.endsWith("\r") ? "\r" : "");
    rewritten.add(name);
  }
  if (!rewritten.has("status")) {
    return { ok: false, error: `${gateFile}: no 'status:' line in frontmatter \u2014 not a gate file (or corrupt)` };
  }
  return { ok: true, content: lines.join("\n") };
}
async function answerGate(opts) {
  const status = opts.decision === "approve" ? "approved" : "rejected";
  if (opts.note !== void 0 && /[\r\n]/.test(opts.note)) {
    return { ok: false, error: "note must be a single line (frontmatter scalars cannot span lines)" };
  }
  const replacements = /* @__PURE__ */ new Map([
    ["status", status],
    ["answered_at", opts.answeredAt ?? isoNowSeconds()],
    ["answered_by", opts.answeredBy === "" ? "" : renderScalar(opts.answeredBy)],
    ["note", opts.note === void 0 ? "" : renderScalar(opts.note)]
  ]);
  let release;
  try {
    release = await acquireLock(opts.lockFile, opts.lockOpts);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
  try {
    let content;
    try {
      content = fs22.readFileSync(opts.gateFile, "utf8");
    } catch (err) {
      return { ok: false, error: `gate file not readable: ${opts.gateFile} (${String(err)})` };
    }
    const rewritten = rewriteAnswerFields(content, replacements, opts.gateFile);
    if (!rewritten.ok) return { ok: false, error: rewritten.error };
    try {
      const tmp = `${opts.gateFile}.tmp`;
      fs22.writeFileSync(tmp, rewritten.content, "utf8");
      fs22.renameSync(tmp, opts.gateFile);
    } catch (err) {
      return { ok: false, error: `cannot write ${opts.gateFile}: ${String(err)}` };
    }
    return { ok: true, gateFile: opts.gateFile, status };
  } finally {
    release();
  }
}

// packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts
import * as fs25 from "node:fs";
import * as path28 from "node:path";

// packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts
import * as fs23 from "node:fs";
import * as path26 from "node:path";
var WORKER_COLS = 8;
function parseWorkerLine(line) {
  const parts = line.split("|");
  if (parts.length !== WORKER_COLS && parts.length !== WORKER_COLS - 1) return void 0;
  const [taskKey, status, cli, provider, taskPath, dispatchedAt, updatedAt, model] = parts.map((s) => s.trim());
  if (!taskKey || taskKey.startsWith("#")) return void 0;
  return {
    taskKey: taskKey ?? "",
    status: status ?? "pending",
    cli: cli ?? "",
    provider: provider ?? "",
    taskPath: taskPath ?? "",
    dispatchedAt: dispatchedAt ?? "",
    updatedAt: updatedAt ?? "",
    model: model ?? ""
  };
}
function serializeWorkerLine(entry) {
  return [
    entry.taskKey,
    entry.status,
    entry.cli,
    entry.provider,
    entry.taskPath,
    entry.dispatchedAt,
    entry.updatedAt,
    entry.model ?? ""
  ].join(" | ");
}
var WorkerStore = class {
  constructor(agenticdocRoot2) {
    this.filePath = path26.join(agenticdocRoot2, "_workers.parallel");
    this.lockPath = path26.join(agenticdocRoot2, "..", ".mw", "workers.lock");
  }
  readAll() {
    if (!fs23.existsSync(this.filePath)) return [];
    const lines = fs23.readFileSync(this.filePath, "utf8").split("\n");
    return lines.map(parseWorkerLine).filter((e) => e !== void 0);
  }
  async upsert(entry) {
    const release = await acquireLock(this.lockPath);
    try {
      const existing = this.readAll();
      const idx = existing.findIndex((e) => e.taskKey === entry.taskKey);
      if (idx >= 0) {
        existing[idx] = entry;
      } else {
        existing.push(entry);
      }
      const content = `${existing.map(serializeWorkerLine).join("\n")}
`;
      const tmpPath = `${this.filePath}.tmp`;
      fs23.writeFileSync(tmpPath, content, "utf8");
      fs23.renameSync(tmpPath, this.filePath);
    } finally {
      release();
    }
  }
  findByKey(taskKey) {
    return this.readAll().find((e) => e.taskKey === taskKey);
  }
};

// packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts
import * as fs24 from "node:fs";
import * as path27 from "node:path";
function autopilotDir(projectDir) {
  return path27.join(projectDir, ".agenticdoc", "_autopilot");
}
function roadmapPath(projectDir) {
  return path27.join(autopilotDir(projectDir), "_roadmap.md");
}
function gatesDir(projectDir) {
  return path27.join(autopilotDir(projectDir), "gates");
}
function timelinePath(projectDir) {
  return path27.join(autopilotDir(projectDir), "timeline.jsonl");
}
function configPath(projectDir) {
  return path27.join(autopilotDir(projectDir), "config.json");
}
function gatesLockPath(projectDir) {
  return path27.join(projectDir, ".mw", "gates.lock");
}
var DEFAULT_CONFIG = {
  enabled: false,
  paused: false,
  poll_interval_sec: 4,
  max_parallel_keys: 2,
  round_budget: 2,
  worker_timeout_min: 30,
  l2_read_file_cap: 8,
  l2_read_byte_cap: 65536,
  advance_stall_ticks: 5
};
var BOOL_FIELDS = ["enabled", "paused"];
var INT_RANGES = {
  poll_interval_sec: [1, 5],
  max_parallel_keys: [2, null],
  round_budget: [1, null],
  worker_timeout_min: [1, null],
  l2_read_file_cap: [1, null],
  l2_read_byte_cap: [1, null],
  advance_stall_ticks: [1, 50]
};
function validateConfigData(data) {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return ["config root must be a JSON object"];
  }
  const cfg = data;
  const errors = [];
  const known = new Set(Object.keys(DEFAULT_CONFIG));
  const unknown = Object.keys(cfg).filter((k) => !known.has(k)).sort();
  if (unknown.length > 0) errors.push(`unknown field(s): ${unknown.join(", ")}`);
  for (const field of BOOL_FIELDS) {
    if (field in cfg && typeof cfg[field] !== "boolean") {
      errors.push(`${field}: expected true/false, got ${JSON.stringify(cfg[field])}`);
    }
  }
  for (const [field, [lo, hi]] of Object.entries(INT_RANGES)) {
    if (!(field in cfg)) continue;
    const value = cfg[field];
    if (typeof value !== "number" || !Number.isInteger(value)) {
      errors.push(`${field}: expected integer, got ${JSON.stringify(value)}`);
      continue;
    }
    if (value < lo) errors.push(`${field}: must be >= ${lo}, got ${value}`);
    if (hi !== null && value > hi) errors.push(`${field}: must be <= ${hi}, got ${value}`);
  }
  return errors;
}
function readConfig(projectDir) {
  const file = configPath(projectDir);
  let raw;
  try {
    raw = fs24.readFileSync(file, "utf8");
  } catch (err) {
    if (err.code === "ENOENT") return { ok: true, config: { ...DEFAULT_CONFIG } };
    return { ok: false, error: `cannot read ${file}: ${String(err)}` };
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch (err) {
    return { ok: false, error: `cannot parse ${file}: ${String(err)}` };
  }
  const errors = validateConfigData(data);
  if (errors.length > 0) return { ok: false, error: `invalid _autopilot/config.json: ${errors.join("; ")}` };
  const cfg = data;
  const boolOf = (name) => typeof cfg[name] === "boolean" ? cfg[name] : DEFAULT_CONFIG[name];
  const intOf = (name) => typeof cfg[name] === "number" ? cfg[name] : DEFAULT_CONFIG[name];
  const merged = {
    enabled: boolOf("enabled"),
    paused: boolOf("paused"),
    poll_interval_sec: intOf("poll_interval_sec"),
    max_parallel_keys: intOf("max_parallel_keys"),
    round_budget: intOf("round_budget"),
    worker_timeout_min: intOf("worker_timeout_min"),
    l2_read_file_cap: intOf("l2_read_file_cap"),
    l2_read_byte_cap: intOf("l2_read_byte_cap"),
    advance_stall_ticks: intOf("advance_stall_ticks")
  };
  return { ok: true, config: merged };
}
function saveConfig(projectDir, config) {
  const errors = validateConfigData(config);
  if (errors.length > 0) return { ok: false, error: `invalid _autopilot/config.json: ${errors.join("; ")}` };
  const ordered = {
    enabled: config.enabled,
    paused: config.paused,
    poll_interval_sec: config.poll_interval_sec,
    max_parallel_keys: config.max_parallel_keys,
    round_budget: config.round_budget,
    worker_timeout_min: config.worker_timeout_min,
    l2_read_file_cap: config.l2_read_file_cap,
    l2_read_byte_cap: config.l2_read_byte_cap,
    advance_stall_ticks: config.advance_stall_ticks
  };
  const file = configPath(projectDir);
  try {
    fs24.mkdirSync(path27.dirname(file), { recursive: true });
    const tmp = `${file}.tmp`;
    fs24.writeFileSync(tmp, `${JSON.stringify(ordered, null, 2)}
`, "utf8");
    fs24.renameSync(tmp, file);
  } catch (err) {
    return { ok: false, error: `cannot write ${file}: ${String(err)}` };
  }
  return { ok: true };
}
var STAGE_STATUSES = ["pending", "approved", "running", "closed", "closed-human", "halted"];
var KEY_STATUSES = ["running", "done", "stalled", "closed-legacy"];
var STAGE_PREFIX_RE = /^##\s*Stage\b/;
var STAGE_HEADER_RE = /^##\s*Stage\s+(\d+)\s*:\s*(.+)$/;
var ROADMAP_FIELD_RE = /^>\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$/;
var SEPARATOR_CELL_RE = /^:?-+:?$/;
function splitTableRow(line) {
  let body = line.startsWith("|") ? line.slice(1) : line;
  if (body.endsWith("|")) body = body.slice(0, -1);
  return body.split("|").map((c) => c.trim());
}
function isKeysHeaderRow(cells) {
  return cells.length === 3 && cells[0].toLowerCase() === "key" && cells[1].toLowerCase() === "role" && cells[2].toLowerCase() === "depends_on";
}
function parseDependsOn(cell) {
  const trimmed = cell.trim();
  if (trimmed === "" || trimmed === "-") return [];
  const deps = [];
  for (const part of trimmed.split(",")) {
    const p = part.trim();
    if (p !== "" && p !== "-") deps.push(p);
  }
  return deps;
}
function parseRoadmapText(text) {
  const warnings = [];
  const stages = [];
  let cur = null;
  let inKeysTable = false;
  let tableHeaderSeen = false;
  const finish = () => {
    if (cur === null) return;
    if (!cur.seenFields.has("status")) {
      warnings.push(`stage ${cur.stage.number}: missing '> status:' line (shown as pending)`);
      cur.stage.status = "pending";
    }
    if (!cur.seenFields.has("goal")) {
      warnings.push(`stage ${cur.stage.number}: missing '> goal:' line`);
    }
    stages.push(cur.stage);
    cur = null;
  };
  const lines = text.split(/\r\n|\r|\n/);
  for (let lineno = 1; lineno <= lines.length; lineno++) {
    const line = lines[lineno - 1].trim();
    if (line === "") continue;
    if (line.startsWith("#")) {
      if (line.startsWith("###")) {
        const heading = line.replace(/^#+/, "").trim();
        if (cur !== null && heading.toLowerCase() === "keys") {
          inKeysTable = true;
          tableHeaderSeen = false;
        } else {
          inKeysTable = false;
        }
        continue;
      }
      if (line.startsWith("##")) {
        if (STAGE_PREFIX_RE.test(line)) {
          const m = STAGE_HEADER_RE.exec(line);
          if (m === null) {
            warnings.push(`line ${lineno}: malformed stage header (expected '## Stage <number>: <title>')`);
            finish();
            inKeysTable = false;
            continue;
          }
          finish();
          cur = {
            stage: {
              number: Number(m[1]),
              title: (m[2] ?? "").trim(),
              goal: "",
              status: "pending",
              keyStatus: {},
              keys: []
            },
            seenKeys: /* @__PURE__ */ new Set(),
            seenFields: /* @__PURE__ */ new Set()
          };
        } else {
          finish();
        }
        inKeysTable = false;
        continue;
      }
      inKeysTable = false;
      continue;
    }
    if (line.startsWith("|")) {
      if (cur !== null && inKeysTable) {
        const cells = splitTableRow(line);
        if (cells.length > 0 && cells.every((c) => SEPARATOR_CELL_RE.test(c))) continue;
        if (!tableHeaderSeen && isKeysHeaderRow(cells)) {
          tableHeaderSeen = true;
          continue;
        }
        if (cells.length !== 3) {
          warnings.push(
            `line ${lineno} (stage ${cur.stage.number}): keys table row must have 3 columns (key | role | depends_on), got ${cells.length}`
          );
          continue;
        }
        const key = cells[0] ?? "";
        if (key === "") {
          warnings.push(`line ${lineno} (stage ${cur.stage.number}): keys table row has empty key cell`);
          continue;
        }
        if (cur.seenKeys.has(key)) {
          warnings.push(`line ${lineno} (stage ${cur.stage.number}): duplicate key row '${key}'`);
          continue;
        }
        cur.seenKeys.add(key);
        cur.stage.keys.push({ key, role: cells[1] ?? "", dependsOn: parseDependsOn(cells[2] ?? "") });
      }
      continue;
    }
    if (line.startsWith(">")) {
      const m = ROADMAP_FIELD_RE.exec(line);
      const name = m?.[1] ?? "";
      const value = (m?.[2] ?? "").trim();
      if (cur !== null) {
        if (name === "goal" || name === "status" || name === "key-status") {
          if (cur.seenFields.has(name)) {
            warnings.push(
              `line ${lineno} (stage ${cur.stage.number}): duplicate '> ${name}:' line (last one wins)`
            );
          } else {
            cur.seenFields.add(name);
          }
          if (name === "goal") cur.stage.goal = value;
          else if (name === "status") {
            if (!STAGE_STATUSES.includes(value)) {
              warnings.push(`line ${lineno} (stage ${cur.stage.number}): invalid status '${value}'`);
            }
            cur.stage.status = value;
          } else {
            parseKeyStatusLine(value, cur.stage, lineno, warnings);
          }
        }
        inKeysTable = false;
      }
      continue;
    }
    inKeysTable = false;
  }
  finish();
  if (stages.length === 0) warnings.push("no '## Stage <number>: <title>' sections found");
  return { stages, warnings };
}
function parseKeyStatusLine(value, stage, lineno, warnings) {
  for (const part of value.split(",")) {
    const entry = part.trim();
    if (entry === "") continue;
    const eq = entry.indexOf("=");
    if (eq <= 0) {
      warnings.push(
        `line ${lineno} (stage ${stage.number}): malformed key-status entry '${entry}' (expected <key>=<status>)`
      );
      continue;
    }
    const key = entry.slice(0, eq).trim();
    const status = entry.slice(eq + 1).trim();
    if (key === "") {
      warnings.push(
        `line ${lineno} (stage ${stage.number}): malformed key-status entry '${entry}' (expected <key>=<status>)`
      );
      continue;
    }
    if (!KEY_STATUSES.includes(status)) {
      warnings.push(`line ${lineno} (stage ${stage.number}): key '${key}' has invalid status '${status}'`);
    }
    if (key in stage.keyStatus) {
      warnings.push(
        `line ${lineno} (stage ${stage.number}): duplicate key-status entry for '${key}' (last one wins)`
      );
    }
    stage.keyStatus[key] = status;
  }
}
function readRoadmap(projectDir) {
  const file = roadmapPath(projectDir);
  let text;
  try {
    text = fs24.readFileSync(file, "utf8");
  } catch {
    return { ok: false, error: `roadmap file not found: ${file}` };
  }
  const parse3 = parseRoadmapText(text);
  return { ok: true, stages: parse3.stages, warnings: parse3.warnings };
}
var GATE_KINDS = ["stage-confirm", "stage-close", "stalled", "budget-exhausted", "goal-change"];
var GATE_STATUSES = ["pending", "approved", "rejected"];
var GATE_FRONTMATTER_FIELDS = [
  "id",
  "kind",
  "stage",
  "key",
  "created_at",
  "created_by",
  "question",
  "context_refs",
  "status",
  "answered_at",
  "answered_by",
  "note"
];
var GateFormatError = class extends Error {
};
var GATE_FILE_RE = /^gate-(\d+)\.md$/;
var GATE_FIELD_LINE_RE2 = /^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?[ \t]*$/;
var GATE_LIST_ITEM_RE = /^[ \t]+-[ \t]+(.*)$/;
var GATE_NULL_LITERALS = /* @__PURE__ */ new Set(["", "~", "-", "null", "Null", "NULL"]);
function gateScalar(raw, file, lineno) {
  if (raw === void 0) return null;
  if (raw.startsWith("'")) {
    if (raw.length < 2 || !raw.endsWith("'")) {
      throw new GateFormatError(`${file}: unterminated single-quoted scalar (line ${lineno}): '${raw}'`);
    }
    return raw.slice(1, -1).replaceAll("''", "'");
  }
  if (raw.startsWith('"')) {
    throw new GateFormatError(`${file}: double-quoted scalars are not supported (line ${lineno}): '${raw}'`);
  }
  if (GATE_NULL_LITERALS.has(raw)) return null;
  return raw;
}
function isIsoTimestamp(value) {
  return !Number.isNaN(Date.parse(value));
}
function parseGateFile(text, file) {
  const lines = text.split(/\r\n|\r|\n/);
  if (lines.length === 0 || lines[0].trim() !== "---") {
    throw new GateFormatError(`${file}: frontmatter must open with a '---' line`);
  }
  const fields = /* @__PURE__ */ new Map();
  const contextRefs = [];
  const seen = /* @__PURE__ */ new Set();
  let inRefs = false;
  let closed = false;
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "---") {
      closed = true;
      break;
    }
    if (inRefs) {
      const item = GATE_LIST_ITEM_RE.exec(line);
      if (item !== null) {
        const ref = gateScalar(item[1], file, i + 1);
        if (ref === null || ref === "")
          throw new GateFormatError(`${file}: empty context_refs item (line ${i + 1})`);
        contextRefs.push(ref);
        continue;
      }
      inRefs = false;
    }
    const field = GATE_FIELD_LINE_RE2.exec(line);
    if (field === null) throw new GateFormatError(`${file}: invalid frontmatter line ${i + 1}: '${line}'`);
    const name = field[1] ?? "";
    if (!GATE_FRONTMATTER_FIELDS.includes(name)) {
      throw new GateFormatError(`${file}: unknown frontmatter field '${name}' (line ${i + 1})`);
    }
    if (seen.has(name)) throw new GateFormatError(`${file}: duplicate frontmatter field '${name}' (line ${i + 1})`);
    seen.add(name);
    const raw = field[2];
    if (name === "context_refs") {
      if (raw === void 0 || raw === "") {
        fields.set(name, null);
        inRefs = true;
      } else if (raw === "[]") {
        fields.set(name, null);
      } else {
        throw new GateFormatError(`${file}: context_refs must be a block list or [] (line ${i + 1})`);
      }
    } else {
      fields.set(name, gateScalar(raw, file, i + 1));
    }
  }
  if (!closed) throw new GateFormatError(`${file}: frontmatter never closes with a '---' line`);
  const required = (name) => {
    const value = fields.get(name);
    if (typeof value !== "string" || value === "") {
      throw new GateFormatError(`${file}: field '${name}' must be a non-empty string`);
    }
    return value;
  };
  const optional = (name) => {
    const value = fields.get(name) ?? null;
    return typeof value === "string" && value !== "" ? value : null;
  };
  const id = required("id");
  if (!/^gate-\d+$/.test(id)) throw new GateFormatError(`${file}: id must match 'gate-<digits>', got '${id}'`);
  const kind = required("kind");
  if (!GATE_KINDS.includes(kind)) {
    throw new GateFormatError(`${file}: unknown kind '${kind}' (expected one of: ${GATE_KINDS.join(", ")})`);
  }
  const status = required("status");
  if (!GATE_STATUSES.includes(status)) {
    throw new GateFormatError(`${file}: unknown status '${status}' (expected one of: ${GATE_STATUSES.join(", ")})`);
  }
  const stageRaw = optional("stage");
  let stage = null;
  if (stageRaw !== null) {
    if (!/^-?\d+$/.test(stageRaw)) throw new GateFormatError(`${file}: stage must be an integer, got '${stageRaw}'`);
    stage = Number.parseInt(stageRaw, 10);
  }
  if (contextRefs.some((r) => r === "")) {
    throw new GateFormatError(`${file}: context_refs must be a list of non-empty strings`);
  }
  const createdAt = required("created_at");
  if (!isIsoTimestamp(createdAt)) {
    throw new GateFormatError(`${file}: created_at is not an ISO-8601 timestamp: '${createdAt}'`);
  }
  const answeredAt = optional("answered_at");
  if (answeredAt !== null && !isIsoTimestamp(answeredAt)) {
    throw new GateFormatError(`${file}: answered_at is not an ISO-8601 timestamp: '${answeredAt}'`);
  }
  required("created_by");
  const question = required("question");
  return {
    id,
    kind,
    status,
    stage,
    key: optional("key"),
    question,
    createdAt,
    path: file
  };
}
function listGates(projectDir) {
  const dir = gatesDir(projectDir);
  const errors = [];
  const found = [];
  let entries;
  try {
    entries = fs24.readdirSync(dir, { withFileTypes: true });
  } catch {
    return { gates: [], errors: [] };
  }
  for (const entry of entries) {
    const m = GATE_FILE_RE.exec(entry.name);
    if (m === null || !entry.isFile()) continue;
    const file = path27.join(dir, entry.name);
    let text;
    try {
      text = fs24.readFileSync(file, "utf8");
    } catch (err) {
      errors.push(`${file}: ${String(err)}`);
      continue;
    }
    try {
      const gate = parseGateFile(text, file);
      if (gate.id !== entry.name.replace(/\.md$/, "")) {
        errors.push(`${file}: frontmatter id '${gate.id}' does not match file name`);
        continue;
      }
      found.push({ seq: Number(m[1]), gate });
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }
  found.sort((a, b) => a.seq - b.seq || a.gate.id.localeCompare(b.gate.id));
  return { gates: found.map((f) => f.gate), errors };
}
var EVENT_TYPES = /* @__PURE__ */ new Set([
  "beat",
  "dispatch",
  "worker-terminal",
  "advance",
  "gate-created",
  "gate-answered",
  "stalled",
  "skip",
  "stage-close",
  "config",
  "goal-halt",
  "goal-snapshot",
  "type-rejected",
  "reconcile",
  "resume",
  "l3-no-verdict"
]);
var BEAT_EV = "beat";
function nonBeatFilter() {
  const filter2 = new Set(EVENT_TYPES);
  filter2.delete(BEAT_EV);
  return filter2;
}
function rotationChain(timelinePath2) {
  const dir = path27.dirname(timelinePath2);
  const prefix = `${path27.basename(timelinePath2)}.`;
  let entries;
  try {
    entries = fs24.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const found = [];
  for (const entry of entries) {
    if (!entry.name.startsWith(prefix)) continue;
    const suffix = entry.name.slice(prefix.length);
    if (/^\d+$/.test(suffix) && entry.isFile()) {
      found.push({ gen: Number(suffix), file: path27.join(dir, entry.name) });
    }
  }
  found.sort((a, b) => b.gen - a.gen);
  return found.map((f) => f.file);
}
function readTimelineEvents(file) {
  let data;
  try {
    data = fs24.readFileSync(file);
  } catch {
    return { events: [], skipped: 0 };
  }
  const events = [];
  let skipped = 0;
  for (const raw of data.toString("utf8").split("\n")) {
    const line = raw.trim();
    if (line === "") continue;
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      skipped += 1;
      continue;
    }
    if (typeof obj !== "object" || obj === null) {
      skipped += 1;
      continue;
    }
    const rec = obj;
    const seq = rec.seq;
    if (typeof seq !== "number" || !Number.isInteger(seq)) {
      skipped += 1;
      continue;
    }
    events.push({
      ts: typeof rec.ts === "string" ? rec.ts : "",
      seq,
      ev: typeof rec.ev === "string" ? rec.ev : "",
      key: typeof rec.key === "string" ? rec.key : "-",
      stage: typeof rec.stage === "number" && Number.isInteger(rec.stage) ? rec.stage : null,
      detail: typeof rec.detail === "string" ? rec.detail : ""
    });
  }
  return { events, skipped };
}
function queryTimeline(timelinePath2, watermark, evFilter) {
  const mark = Number.isInteger(watermark) && watermark > 0 ? watermark : 0;
  const all = [];
  let skipped = 0;
  for (const source of [...rotationChain(timelinePath2), timelinePath2]) {
    const result = readTimelineEvents(source);
    all.push(...result.events);
    skipped += result.skipped;
  }
  all.sort((a, b) => a.seq - b.seq);
  const last = all.length > 0 ? all[all.length - 1] : void 0;
  let pruned;
  if (all.length > 0) {
    pruned = Math.max(0, all[0].seq - mark - 1);
  } else {
    pruned = mark > 0 ? mark : 0;
  }
  const events = all.filter((e) => e.seq > mark && (evFilter === void 0 || evFilter.has(e.ev)));
  return { events, pruned, skipped, head: last === void 0 ? void 0 : { seq: last.seq, ts: last.ts } };
}
function watermarkFromSince(timelinePath2, sinceIso) {
  const since = Date.parse(sinceIso);
  if (Number.isNaN(since)) return 0;
  let mark = 0;
  for (const source of [...rotationChain(timelinePath2), timelinePath2]) {
    for (const ev of readTimelineEvents(source).events) {
      const ts = Date.parse(ev.ts);
      if (!Number.isNaN(ts) && ts <= since && ev.seq > mark) mark = ev.seq;
    }
  }
  return mark;
}
var TASK_FM_LINE_RE = /^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$/;
function parseTaskLabels(taskMdPath) {
  let text;
  try {
    text = fs24.readFileSync(taskMdPath, "utf8");
  } catch {
    return /* @__PURE__ */ new Map();
  }
  const lines = text.split(/\r\n|\r|\n/);
  if (lines.length === 0 || lines[0].trim() !== "---") return /* @__PURE__ */ new Map();
  const labels = /* @__PURE__ */ new Map();
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "---") break;
    const m = TASK_FM_LINE_RE.exec(line);
    if (m === null) continue;
    labels.set(m[1] ?? "", m[2] ?? "");
  }
  return labels;
}
function usedRounds(workersDirs) {
  const units = /* @__PURE__ */ new Map();
  for (const workersDir of workersDirs) {
    let entries;
    try {
      entries = fs24.readdirSync(workersDir, { withFileTypes: true });
    } catch {
      continue;
    }
    const names = entries.filter((e) => e.isDirectory()).map((e) => e.name).sort();
    for (const name of names) {
      const labels = parseTaskLabels(path27.join(workersDir, name, "task.md"));
      const loop = labels.get("loop");
      if (loop === void 0 || loop === "") continue;
      const attempt = (labels.get("attempt") ?? "").trim();
      const unit = attempt !== "" ? attempt : `@${name}`;
      let attempts = units.get(loop);
      if (attempts === void 0) {
        attempts = /* @__PURE__ */ new Set();
        units.set(loop, attempts);
      }
      attempts.add(unit);
    }
  }
  const result = /* @__PURE__ */ new Map();
  for (const [loop, attempts] of units) result.set(loop, attempts.size);
  return result;
}
var STATUS_SCHEMA = "autopilot-status/1";
function currentStage(stages) {
  if (stages.length === 0) return void 0;
  const running = stages.find((s) => s.status === "running");
  if (running !== void 0) return running;
  const open = stages.find((s) => s.status !== "closed" && s.status !== "closed-human");
  return open ?? stages[stages.length - 1];
}
function keyRounds(perLoop, key, budget) {
  let l2 = 0;
  let l3 = 0;
  let retry = 0;
  for (const [loop, used] of perLoop) {
    if (loop.startsWith(`l2:${key}:`)) l2 = Math.max(l2, used);
    else if (loop === `l3:${key}`) l3 = Math.max(l3, used);
    else if (loop.startsWith(`exec:${key}:`) || loop === `repair:${key}`) retry = Math.max(retry, used);
  }
  return {
    l2: { used: l2, max: budget },
    l3: { used: l3, max: budget },
    retry: { used: retry, max: budget }
  };
}
function deriveStatusModel(projectDir) {
  const cfg = readConfig(projectDir);
  if (!cfg.ok) return cfg;
  const config = cfg.config;
  const warnings = [];
  const roadmap = readRoadmap(projectDir);
  if (roadmap.ok) {
    warnings.push(...roadmap.warnings);
  } else {
    warnings.push(roadmap.error);
  }
  const stage = currentStage(roadmap.ok ? roadmap.stages : []);
  const agenticdoc = path27.join(projectDir, ".agenticdoc");
  const phaseByKey = new Map(new IndexStore(agenticdoc).readAll().map((e) => [e.key, e.phase]));
  const keys = [];
  if (stage !== void 0) {
    for (const row of stage.keys) {
      const perLoop = usedRounds([path27.join(agenticdoc, row.key, "workers")]);
      keys.push({
        key: row.key,
        phase: phaseByKey.get(row.key) ?? "\u2014",
        // key-status line absent (fresh proposal) → the only non-terminal
        // enum value, "running" (D-105 KEY_STATUSES has no "pending").
        state: stage.keyStatus[row.key] ?? "running",
        rounds: keyRounds(perLoop, row.key, config.round_budget)
      });
    }
  }
  const gateScan = listGates(projectDir);
  warnings.push(...gateScan.errors);
  const gates = gateScan.gates.map((g) => ({ id: g.id, kind: g.kind, status: g.status }));
  const head = queryTimeline(timelinePath(projectDir), 0).head;
  return {
    ok: true,
    model: {
      status: {
        schema: STATUS_SCHEMA,
        stage: {
          current: stage === void 0 ? 0 : stage.number,
          status: stage === void 0 ? "none" : stage.status,
          keys
        },
        gates,
        timeline: head === void 0 ? { seq: 0, ts: "" } : { seq: head.seq, ts: head.ts },
        config: {
          enabled: config.enabled,
          poll_interval_sec: config.poll_interval_sec,
          round_budget: config.round_budget,
          max_parallel_keys: config.max_parallel_keys
        }
      },
      paused: config.paused,
      warnings
    }
  };
}
function renderStatusText(model) {
  const { status, paused, warnings } = model;
  const lines = [];
  if (status.stage.current > 0) {
    lines.push(`stage ${status.stage.current} (${status.stage.status})`);
    for (const k of status.stage.keys) {
      lines.push(
        `  ${k.key} | phase=${k.phase} | state=${k.state} | L2 ${k.rounds.l2.used}/${k.rounds.l2.max} | L3 ${k.rounds.l3.used}/${k.rounds.l3.max} | retry ${k.rounds.retry.used}/${k.rounds.retry.max}`
      );
    }
    if (status.stage.keys.length === 0) lines.push("  (no keys)");
  } else {
    lines.push("stage: none (no roadmap \u2014 autopilot not initialized or no stages parsed)");
  }
  const pending = status.gates.filter((g) => g.status === "pending");
  lines.push(`gates: ${status.gates.length} total, ${pending.length} pending`);
  for (const g of status.gates) lines.push(`  ${g.id} ${g.kind} ${g.status}`);
  lines.push(`timeline: seq=${status.timeline.seq} ts=${status.timeline.ts}`);
  lines.push(
    `config: enabled=${status.config.enabled} | poll_interval_sec=${status.config.poll_interval_sec} | round_budget=${status.config.round_budget} | max_parallel_keys=${status.config.max_parallel_keys}${paused ? " | paused" : ""}`
  );
  for (const w of warnings) lines.push(`warning: ${w}`);
  return lines.join("\n");
}

// packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts
var MONITOR_WIDGET_ID = "agent-team-loop-monitor";
var MONITOR_INTERVAL_MS = 4e3;
var MONITOR_LINE_MAX = 110;
function scanPendingGate(file) {
  let text;
  try {
    text = fs25.readFileSync(file, "utf8");
  } catch {
    return null;
  }
  const lines = text.split(/\r\n|\r|\n/);
  if (lines.length === 0 || lines[0].trim() !== "---") return null;
  let id = "";
  let kind = "";
  let stage = null;
  let key = "";
  let status = "";
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "---") break;
    const m = /^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*$/.exec(line);
    if (m === null) continue;
    const name = m[1] ?? "";
    const value = m[2] ?? "";
    if (name === "id") id = value;
    else if (name === "kind") kind = value;
    else if (name === "status") status = value;
    else if (name === "key") key = value;
    else if (name === "stage") stage = /^-?\d+$/.test(value) ? Number.parseInt(value, 10) : null;
  }
  if (status !== "pending" || id === "" || kind === "") return null;
  return { id, kind, stage, key };
}
function readMonitorState(projectDir, nowMs) {
  const status = getMwStatus(projectDir);
  let serve = { running: false, pid: null, stale: false, staleDetail: "", upMs: null };
  if (status.running) {
    const staleness = serveStaleness(projectDir);
    let startedAtMs = readServeMeta(projectDir)?.startedAtMs ?? null;
    if (startedAtMs === null) {
      try {
        startedAtMs = fs25.statSync(path28.join(projectDir, ".mw", "mw.pid")).mtimeMs;
      } catch {
        startedAtMs = null;
      }
    }
    serve = {
      running: true,
      pid: status.pid,
      stale: staleness?.stale ?? false,
      staleDetail: staleness?.detail ?? "",
      upMs: startedAtMs === null ? null : Math.max(0, nowMs - startedAtMs)
    };
  }
  let conductorPid = null;
  let conductorAlive = false;
  try {
    const raw = fs25.readFileSync(path28.join(projectDir, ".mw", "conductor.pid"), "utf8").trim();
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isNaN(parsed)) {
      conductorPid = parsed;
      try {
        process.kill(parsed, 0);
        conductorAlive = true;
      } catch {
        conductorAlive = false;
      }
    }
  } catch {
  }
  let everEnabled = false;
  let enabled = false;
  let paused = false;
  if (fs25.existsSync(configPath(projectDir))) {
    const cfg = readConfig(projectDir);
    if (cfg.ok) {
      everEnabled = true;
      enabled = cfg.config.enabled;
      paused = cfg.config.paused;
    }
  }
  const conductor = { pid: conductorPid, alive: conductorAlive, enabled, paused, everEnabled };
  const workers = [];
  for (const entry of new WorkerStore(path28.join(projectDir, ".agenticdoc")).readAll()) {
    if (entry.status !== "running") continue;
    const dispatched = Date.parse(entry.dispatchedAt);
    if (Number.isNaN(dispatched)) continue;
    workers.push({ taskKey: entry.taskKey, elapsedMs: Math.max(0, nowMs - dispatched) });
  }
  workers.sort((a, b) => b.elapsedMs - a.elapsedMs || a.taskKey.localeCompare(b.taskKey));
  const gates = [];
  try {
    const dir = gatesDir(projectDir);
    for (const entry of fs25.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isFile() || !/^gate-\d+\.md$/.test(entry.name)) continue;
      const gate = scanPendingGate(path28.join(dir, entry.name));
      if (gate !== null) gates.push(gate);
    }
  } catch {
  }
  gates.sort((a, b) => a.id.localeCompare(b.id));
  const autopilot = deriveAutopilotPanel(projectDir, nowMs, workers);
  return { serve, conductor, autopilot, workers, gates };
}
function readTimelineTail(file, opts) {
  const maxBytes = opts?.maxBytes ?? 512 * 1024;
  const limit = opts?.limit ?? 400;
  let fd;
  try {
    fd = fs25.openSync(file, "r");
  } catch {
    return [];
  }
  try {
    const size = fs25.fstatSync(fd).size;
    if (size <= 0) return [];
    const start = Math.max(0, size - maxBytes);
    const buf = Buffer.alloc(size - start);
    fs25.readSync(fd, buf, 0, buf.length, start);
    let lines = buf.toString("utf8").split("\n");
    if (start > 0) lines = lines.slice(1);
    const events = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed === "") continue;
      let parsed;
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        continue;
      }
      if (typeof parsed !== "object" || parsed === null) continue;
      const ev = parsed;
      if (typeof ev.seq !== "number") continue;
      events.push({
        ts: typeof ev.ts === "string" ? ev.ts : "",
        seq: ev.seq,
        ev: typeof ev.ev === "string" ? ev.ev : "",
        key: typeof ev.key === "string" ? ev.key : "-",
        stage: typeof ev.stage === "number" ? ev.stage : null,
        detail: typeof ev.detail === "string" ? ev.detail : ""
      });
    }
    return limit > 0 && events.length > limit ? events.slice(-limit) : events;
  } catch {
    return [];
  } finally {
    fs25.closeSync(fd);
  }
}
var ADVANCE_DETAIL_RE = /^(\S+) exit=(\d+)(?: class=(\S+))?$/;
var INTERFACE_DRIFT_MARKERS = [
  "unknown phase",
  "valid: spec",
  "phase-line",
  "phase field",
  "unsupported framework",
  "framework version"
];
var GATE_BLOCKED_MARKERS = [
  "gate blocked",
  "gate fail",
  "missing:",
  "missing prerequisite",
  "\u7F3A\u5C11",
  "not met",
  "\u672A\u6EE1\u8DB3"
];
var TIMEOUT_ENV_MARKERS = ["timeout", "timed out", "locate", "advanceerror", "no such file", "cannot find"];
function classifyAdvanceFailure(text) {
  const low = text.toLowerCase();
  if (INTERFACE_DRIFT_MARKERS.some((m) => low.includes(m))) return "interface-drift";
  if (GATE_BLOCKED_MARKERS.some((m) => low.includes(m))) return "gate-blocked";
  if (TIMEOUT_ENV_MARKERS.some((m) => low.includes(m))) return "timeout-env";
  return "other";
}
function deriveAdvanceStalls(events, nowMs) {
  const active = /* @__PURE__ */ new Map();
  const cleared = /* @__PURE__ */ new Set();
  const pendingError = /* @__PURE__ */ new Map();
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev === void 0) continue;
    const key = ev.key;
    if (key === "" || key === "-") continue;
    if (ev.ev === "config") {
      if (!pendingError.has(key) && ev.detail.includes("advance")) {
        pendingError.set(
          key,
          ev.detail.slice(ev.detail.indexOf(":") + 1).trim().slice(0, 120)
        );
      }
      continue;
    }
    if (ev.ev !== "advance") continue;
    const m = ADVANCE_DETAIL_RE.exec(ev.detail);
    if (m === null) continue;
    const edge = m[1] ?? "";
    if (cleared.has(`${key}|${edge}`)) continue;
    const exitCode = Number.parseInt(m[2] ?? "0", 10);
    if (exitCode === 0) {
      const activeEntry = active.get(key);
      if (activeEntry !== void 0 && activeEntry.edge === edge) active.delete(key);
      cleared.add(`${key}|${edge}`);
      continue;
    }
    const acc = active.get(key);
    if (acc !== void 0) {
      if (acc.edge !== edge) continue;
      acc.count += 1;
      const cls2 = m[3] ?? classifyAdvanceFailure(acc.lastError);
      acc.classes[cls2] = (acc.classes[cls2] ?? 0) + 1;
      continue;
    }
    const lastError = pendingError.get(key) ?? "";
    const cls = m[3] ?? classifyAdvanceFailure(lastError);
    active.set(key, { edge, count: 1, classes: { [cls]: 1 }, lastError, newestTs: ev.ts });
  }
  const stalls = [];
  for (const [key, acc] of active) {
    const ranked = Object.entries(acc.classes).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const parsed = Date.parse(acc.newestTs);
    stalls.push({
      key,
      edge: acc.edge,
      count: acc.count,
      primaryClass: ranked[0]?.[0] ?? "other",
      classCounts: acc.classes,
      lastError: acc.lastError,
      ageMs: Number.isNaN(parsed) ? null : Math.max(0, nowMs - parsed)
    });
  }
  stalls.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
  return stalls;
}
function defaultIndexPhases(projectDir) {
  try {
    const entries = new IndexStore(path28.join(projectDir, ".agenticdoc")).readAll();
    return new Map(entries.map((e) => [e.key, e.phase]));
  } catch {
    return /* @__PURE__ */ new Map();
  }
}
function deriveAutopilotPanel(projectDir, nowMs, workers, deps) {
  const configResult = (deps?.readConfigFile ?? readConfig)(projectDir);
  const config = configResult.ok ? configResult.config : null;
  const roadmap = (deps?.readRoadmapFile ?? readRoadmap)(projectDir);
  const statusByKey = /* @__PURE__ */ new Map();
  const depsByKey = /* @__PURE__ */ new Map();
  if (roadmap.ok) {
    for (const stage of roadmap.stages) {
      for (const [key, status] of Object.entries(stage.keyStatus)) statusByKey.set(key, status);
      for (const row of stage.keys) depsByKey.set(row.key, row.dependsOn);
    }
  }
  const phaseByKey = (deps?.readIndexPhases ?? defaultIndexPhases)(projectDir);
  const events = (deps?.readTimeline ?? ((file) => readTimelineTail(file)))(timelinePath(projectDir));
  let tickSeq = null;
  let tickAgeMs = null;
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev === void 0 || ev.ev !== BEAT_EV) continue;
    tickSeq = ev.seq;
    const parsed = Date.parse(ev.ts);
    tickAgeMs = Number.isNaN(parsed) ? null : Math.max(0, nowMs - parsed);
    break;
  }
  const pollMs = (config?.poll_interval_sec ?? DEFAULT_CONFIG.poll_interval_sec) * 1e3;
  const staleAfterMs = Math.max(3e4, pollMs * 5);
  const keys = [];
  const allKeys = [.../* @__PURE__ */ new Set([...statusByKey.keys(), ...phaseByKey.keys()])].sort();
  for (const key of allKeys) {
    keys.push({
      key,
      phase: phaseByKey.get(key) ?? "\u2014",
      status: statusByKey.get(key) ?? "unknown",
      inFlight: workers.filter((w) => w.taskKey.startsWith(`ap-${key}-`)).length,
      blockedBy: (depsByKey.get(key) ?? []).filter(
        (dep) => !["done", "closed-legacy"].includes(statusByKey.get(dep) ?? "")
      )
    });
  }
  const busyKeys = /* @__PURE__ */ new Set();
  for (const w of workers) {
    const owner = allKeys.find((key) => w.taskKey.startsWith(`ap-${key}-`));
    busyKeys.add(owner ?? w.taskKey);
  }
  return {
    enabled: config?.enabled ?? false,
    everEnabled: fs25.existsSync(configPath(projectDir)) && configResult.ok,
    tickSeq,
    tickAgeMs,
    tickStale: tickAgeMs !== null && tickAgeMs > staleAfterMs,
    slotsUsed: busyKeys.size,
    slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys,
    stallTicks: config?.advance_stall_ticks ?? DEFAULT_CONFIG.advance_stall_ticks,
    keys,
    stalls: deriveAdvanceStalls(events, nowMs)
  };
}
function trunc2(s, max) {
  return s.length <= max ? s : `${s.slice(0, max - 1)}\u2026`;
}
function formatDuration(ms) {
  const s = Math.max(0, Math.floor(ms / 1e3));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}
function conductorIntent(c) {
  if (!c.enabled) return "autopilot disabled";
  return c.paused ? "autopilot enabled, paused" : "autopilot enabled, not paused";
}
function renderMonitorLines(s) {
  const lines = ["[autopilot monitor]"];
  if (!s.serve.running) {
    lines.push("serve: not running -> /mw restart");
  } else if (s.serve.stale) {
    const head = `serve: PID ${s.serve.pid} STALE CODE`;
    const tail = " -> /mw restart";
    const room = MONITOR_LINE_MAX - head.length - tail.length - 3;
    let detail = s.serve.staleDetail;
    if (detail.length > room) detail = `${detail.slice(0, Math.max(0, room - 1))}\u2026`;
    lines.push(`${head} (${detail})${tail}`);
  } else {
    const up = s.serve.upMs !== null ? `, up ${formatDuration(s.serve.upMs)}` : "";
    lines.push(trunc2(`serve: PID ${s.serve.pid ?? "?"} fresh${up}`, MONITOR_LINE_MAX));
  }
  if (!s.conductor.everEnabled) {
    lines.push("conductor: not enabled (/autopilot enable)");
  } else if (s.conductor.pid !== null && s.conductor.alive) {
    lines.push(trunc2(`conductor: PID ${s.conductor.pid} alive | ${conductorIntent(s.conductor)}`, MONITOR_LINE_MAX));
  } else if (s.conductor.pid !== null) {
    lines.push(`conductor: dead (pid ${s.conductor.pid} stale)`);
  } else {
    lines.push(trunc2(`conductor: not running | ${conductorIntent(s.conductor)}`, MONITOR_LINE_MAX));
  }
  if (s.autopilot.enabled) {
    const a = s.autopilot;
    const tick = a.tickSeq === null ? "tick: none yet" : `tick seq ${a.tickSeq} (${a.tickAgeMs === null ? "\u2014" : formatDuration(a.tickAgeMs)} ago)`;
    const stale = a.tickStale ? " STALE (conductor not ticking)" : "";
    const count2 = (status) => a.keys.filter((k) => k.status === status).length;
    lines.push(
      trunc2(
        `autopilot: ${tick}${stale} | slots ${a.slotsUsed}/${a.slotsMax} | keys ${a.keys.length} (running ${count2("running")}, stalled ${count2("stalled")}, done ${count2("done")}) | stall-ticks ${a.stallTicks}`,
        MONITOR_LINE_MAX
      )
    );
    const stallByKey = new Map(a.stalls.map((stall) => [stall.key, stall]));
    const attention = a.keys.filter(
      (k) => k.status === "stalled" || k.inFlight > 0 || k.blockedBy.length > 0 || stallByKey.has(k.key)
    );
    for (const k of attention.slice(0, 6)) {
      const stall = stallByKey.get(k.key);
      const bits = [`  \xB7 ${k.key} ${k.phase}/${k.status}`];
      if (k.inFlight > 0) bits.push(`${k.inFlight} running`);
      if (stall !== void 0) {
        const error = stall.lastError === "" ? "" : ` "${stall.lastError}"`;
        bits.push(
          `advance ${stall.count}x ${stall.primaryClass} ${stall.ageMs === null ? "\u2014" : formatDuration(stall.ageMs)} ago${error}`
        );
      }
      if (k.blockedBy.length > 0) bits.push(`deps blocked by ${k.blockedBy.join(",")}`);
      if (k.status === "stalled") {
        const gate = s.gates.find((g) => g.kind === "stalled" && g.key === k.key);
        const hint = gate === void 0 ? "-> /autopilot gate <id> approve|reject" : `-> /autopilot gate ${gate.id} approve|reject`;
        bits.push(gate === void 0 ? hint : `${hint} (resume grants one round)`);
      }
      lines.push(trunc2(bits.join(" | "), MONITOR_LINE_MAX));
    }
    if (attention.length > 6) lines.push(`  \xB7 +${attention.length - 6} more -> /autopilot status`);
  } else if (!s.autopilot.everEnabled) {
    lines.push("autopilot: not enabled (/autopilot enable)");
  } else {
    lines.push("autopilot: disabled (config.json enabled=false)");
  }
  if (s.workers.length === 0) {
    lines.push("workers: 0 running");
  } else {
    lines.push(`workers: ${s.workers.length} running (all keys)`);
    for (const w of s.workers) {
      lines.push(trunc2(`  \xB7 ${w.taskKey}  ${Math.ceil(w.elapsedMs / 6e4)}m`, MONITOR_LINE_MAX));
    }
  }
  if (s.gates.length === 0) {
    lines.push("gates: 0 pending");
  } else if (s.gates.length === 1) {
    const g = s.gates[0];
    lines.push(
      trunc2(`gates: 1 pending - ${g.id} (${g.kind}) -> /autopilot gate ${g.id} approve|reject`, MONITOR_LINE_MAX)
    );
  } else {
    const list = s.gates.map((g) => `${g.id} (${g.kind})`).join(", ");
    lines.push(trunc2(`gates: ${s.gates.length} pending - ${list} -> /autopilot gates`, MONITOR_LINE_MAX));
  }
  return lines;
}
var monitorTimer = null;
var monitorApply = null;
function isMonitorActive() {
  return monitorTimer !== null;
}
function startMonitor(projectDir, apply, opts) {
  if (monitorTimer !== null) return true;
  const readState = opts?.readState ?? readMonitorState;
  const nowMs = opts?.nowMs ?? Date.now;
  const render = () => {
    try {
      apply(renderMonitorLines(readState(projectDir, nowMs())));
    } catch {
    }
  };
  render();
  monitorApply = apply;
  monitorTimer = setInterval(render, opts?.intervalMs ?? MONITOR_INTERVAL_MS);
  return true;
}
function stopMonitor(apply) {
  if (monitorTimer === null) return false;
  clearInterval(monitorTimer);
  monitorTimer = null;
  const clear = apply ?? monitorApply;
  monitorApply = null;
  clear?.(void 0);
  return true;
}

// packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts
var AUTOPILOT_SEEN_ENTRY_TYPE = "agent-team-loop:autopilot-seen";
var USAGE = "Usage: /autopilot status [--json] | gates | gate <id> approve|reject [--note <text>] | timeline [--since <iso>] [--all] | enable | disable | pause | resume | roadmap | monitor [on|off]";
function registerAutopilotCommands(pi, projectDir, deps = {}) {
  pi.registerCommand("autopilot", {
    description: "Autopilot console: status / gates / gate / timeline / enable / disable / pause / resume / roadmap / monitor",
    handler: async (args, ctx) => {
      const tokens = args.trim().split(/\s+/).filter((t) => t !== "");
      const sub = tokens[0] ?? "";
      const rest = tokens.slice(1);
      switch (sub) {
        case "status":
          cmdStatus(pi, ctx, projectDir, rest);
          return;
        case "gates":
          cmdGates(ctx, projectDir);
          return;
        case "gate":
          await cmdGate(ctx, projectDir, rest);
          return;
        case "timeline":
          cmdTimeline(pi, ctx, projectDir, rest);
          return;
        case "enable":
          cmdSetEnabled(ctx, projectDir, true, deps);
          return;
        case "disable":
          cmdSetEnabled(ctx, projectDir, false, deps);
          return;
        case "pause":
          cmdSetPaused(ctx, projectDir, true);
          return;
        case "resume":
          cmdSetPaused(ctx, projectDir, false);
          return;
        case "roadmap":
          cmdRoadmap(ctx, projectDir);
          return;
        case "monitor":
          cmdMonitor(ctx, projectDir, deps, rest);
          return;
        default:
          ctx.ui.notify(USAGE, "warning");
          return;
      }
    }
  });
}
function readSeenWatermark(ctx) {
  try {
    const entries = ctx.sessionManager.getEntries();
    for (let i = entries.length - 1; i >= 0; i--) {
      const e = entries[i];
      if (e.type !== "custom" || e.customType !== AUTOPILOT_SEEN_ENTRY_TYPE) continue;
      const data = e.data;
      if (data !== void 0 && typeof data.seq === "number" && Number.isInteger(data.seq) && typeof data.ts === "string") {
        return { seq: data.seq, ts: data.ts };
      }
    }
  } catch {
  }
  return void 0;
}
function cmdStatus(pi, ctx, projectDir, rest) {
  const json = rest.includes("--json");
  const result = deriveStatusModel(projectDir);
  if (!result.ok) {
    ctx.ui.notify(`[autopilot] status unavailable: ${result.error}`, "error");
    return;
  }
  const head = result.model.status.timeline;
  if (head.seq > 0) pi.appendEntry(AUTOPILOT_SEEN_ENTRY_TYPE, { seq: head.seq, ts: head.ts });
  ctx.ui.notify(json ? JSON.stringify(result.model.status, null, 2) : renderStatusText(result.model), "info");
}
function cmdGates(ctx, projectDir) {
  const { gates, errors } = listGates(projectDir);
  const pending = gates.filter((g) => g.status === "pending");
  const lines = [];
  if (pending.length === 0) {
    lines.push(`no pending gates (${gates.length} total)`);
  } else {
    lines.push(`${pending.length} pending gate(s):`);
    for (const g of pending) {
      const scope = [g.stage !== null ? `stage=${g.stage}` : null, g.key !== null ? `key=${g.key}` : null].filter((s) => s !== null).join(" ");
      lines.push(`  ${g.id} [${g.kind}]${scope === "" ? "" : ` ${scope}`} \u2014 ${g.question} (created ${g.createdAt})`);
      lines.push(`    answer: /autopilot gate ${g.id} approve|reject [--note <text>]  (${g.path})`);
    }
  }
  for (const e of errors) lines.push(`warning: ${e}`);
  ctx.ui.notify(lines.join("\n"), "info");
}
async function cmdGate(ctx, projectDir, rest) {
  const id = rest[0] ?? "";
  const decision = rest[1] ?? "";
  if (id === "" || decision !== "approve" && decision !== "reject") {
    ctx.ui.notify("Usage: /autopilot gate <id> approve|reject [--note <text>]", "warning");
    return;
  }
  if (!/^gate-\d+$/.test(id)) {
    ctx.ui.notify(`[autopilot] invalid gate id '${id}' (expected gate-<digits>)`, "error");
    return;
  }
  let note;
  const noteIdx = rest.indexOf("--note");
  if (noteIdx >= 0)
    note = rest.slice(noteIdx + 1).join(" ").trim() || void 0;
  const result = await answerGate({
    gateFile: path29.join(gatesDir(projectDir), `${id}.md`),
    lockFile: gatesLockPath(projectDir),
    decision,
    note,
    answeredBy: windowClaimId()
  });
  if (result.ok) {
    ctx.ui.notify(
      `[autopilot] ${id} ${result.status} (by ${windowClaimId()}) \u2014 the conductor reads the answer within one poll interval (<=5s).`,
      "info"
    );
    return;
  }
  ctx.ui.notify(`[autopilot] gate answer failed: ${result.error}`, "error");
  const pending = listGates(projectDir).gates.filter((g) => g.status === "pending");
  if (pending.length > 0) ctx.ui.notify(`pending gates: ${pending.map((g) => g.id).join(", ")}`, "info");
}
function cmdTimeline(pi, ctx, projectDir, rest) {
  const all = rest.includes("--all");
  let since;
  const sinceIdx = rest.indexOf("--since");
  if (sinceIdx >= 0) since = rest[sinceIdx + 1];
  if (since !== void 0 && Number.isNaN(Date.parse(since))) {
    ctx.ui.notify(`[autopilot] invalid --since value '${since}' (expected an ISO-8601 timestamp)`, "error");
    return;
  }
  const tlPath = timelinePath(projectDir);
  let mark = 0;
  if (since !== void 0) mark = watermarkFromSince(tlPath, since);
  else if (!all) mark = readSeenWatermark(ctx)?.seq ?? 0;
  const query = queryTimeline(tlPath, mark, all ? void 0 : nonBeatFilter());
  ctx.ui.notify(renderTimelineText(query, mark), "info");
  if (query.head !== void 0) {
    pi.appendEntry(AUTOPILOT_SEEN_ENTRY_TYPE, { seq: query.head.seq, ts: query.head.ts });
  }
}
function renderTimelineText(query, mark) {
  const lines = [`timeline replay (from seq=${mark}) \u2014 ${query.events.length} event(s)`];
  if (query.pruned > 0) lines.push(`${query.pruned} events pruned (older than the retained rotation generations)`);
  for (const ev of query.events) {
    const stage = ev.stage === null ? "" : ` stage=${ev.stage}`;
    const detail = ev.detail === "" ? "" : ` ${ev.detail}`;
    lines.push(`${ev.seq} ${ev.ts} ${ev.ev} key=${ev.key}${stage}${detail}`);
  }
  if (query.events.length === 0) lines.push("(no events)");
  if (query.skipped > 0) lines.push(`${query.skipped} unparsable line(s) skipped`);
  return lines.join("\n");
}
async function cmdSetEnabled(ctx, projectDir, enabled, deps) {
  const cfg = readConfig(projectDir);
  if (!cfg.ok) {
    ctx.ui.notify(`[autopilot] ${cfg.error}`, "error");
    return;
  }
  const saved = saveConfig(projectDir, { ...cfg.config, enabled });
  if (!saved.ok) {
    ctx.ui.notify(`[autopilot] ${saved.error}`, "error");
    return;
  }
  if (!enabled) {
    ctx.ui.notify(
      "[autopilot] disabled \u2014 mw serve stops the conductor on its next config poll (if running).",
      "info"
    );
    return;
  }
  const outcome = await (deps.ensureMwRunning ?? defaultEnsureMwRunning)(projectDir);
  if (outcome === "started") {
    ctx.ui.notify(
      "[autopilot] enabled + mw serve starting \u2014 the conductor spawns within ~1s of serve startup (AC-025).",
      "info"
    );
  } else if (outcome === "restarted") {
    ctx.ui.notify("[autopilot] enabled \u2014 stale serve restarted; the conductor spawns within ~1s (AC-025).", "info");
  } else if (outcome === "already-running") {
    ctx.ui.notify(
      "[autopilot] enabled \u2014 mw serve is running and spawns the conductor on its next config poll (<=1s).",
      "info"
    );
  } else {
    ctx.ui.notify("[autopilot] enabled, but mw serve could not be started \u2014 run /mw start or set MW_PY.", "warning");
  }
}
async function defaultEnsureMwRunning(projectDir) {
  if (getMwStatus(projectDir).running) {
    const stale = serveStaleness(projectDir);
    if (stale?.stale) {
      const r = await restartMw(projectDir);
      if (r === "restarted") return "restarted";
      return "spawn-failed";
    }
    return "already-running";
  }
  return startMw(projectDir) ? "started" : "spawn-failed";
}
function cmdSetPaused(ctx, projectDir, paused) {
  const cfg = readConfig(projectDir);
  if (!cfg.ok) {
    ctx.ui.notify(`[autopilot] ${cfg.error}`, "error");
    return;
  }
  const saved = saveConfig(projectDir, { ...cfg.config, paused });
  if (!saved.ok) {
    ctx.ui.notify(`[autopilot] ${saved.error}`, "error");
    return;
  }
  ctx.ui.notify(
    paused ? "[autopilot] paused \u2014 the conductor stays alive but dispatches nothing until /autopilot resume." : "[autopilot] resumed \u2014 the conductor resumes dispatching on its next tick.",
    "info"
  );
}
function cmdMonitor(ctx, projectDir, deps, rest) {
  if (!ctx.hasUI) {
    ctx.ui.notify(
      "[autopilot] monitor needs a visual UI \u2014 there is no visual UI in this mode, so no panel was started.",
      "warning"
    );
    return;
  }
  const arg = rest[0] ?? "";
  if (arg !== "" && arg !== "on" && arg !== "off") {
    ctx.ui.notify("Usage: /autopilot monitor [on|off]", "warning");
    return;
  }
  const apply = (lines) => {
    ctx.ui.setWidget(MONITOR_WIDGET_ID, lines, { placement: "belowEditor" });
  };
  if (arg === "off" || arg === "" && isMonitorActive()) {
    const stopped = stopMonitor(apply);
    if (arg === "off") monitorSuppressed = true;
    ctx.ui.notify(
      stopped ? "[autopilot] monitor off \u2014 bottom panel cleared." : "[autopilot] monitor was not running.",
      "info"
    );
    return;
  }
  monitorSuppressed = false;
  startMonitor(projectDir, apply, { intervalMs: deps.monitorIntervalMs, readState: deps.readMonitorState });
  ctx.ui.notify(
    "[autopilot] monitor on \u2014 serve/conductor/autopilot/workers/gates panel below the editor, refreshed every 4s. /autopilot monitor off closes it.",
    "info"
  );
}
var monitorSuppressed = false;
function autoStartMonitor(ctx, projectDir, deps = {}) {
  if (!ctx.hasUI) return false;
  if (deps.autoMonitor === false) return false;
  if (monitorSuppressed) return false;
  if (isMonitorActive()) return true;
  const cfg = readConfig(projectDir);
  if (!cfg.ok || !cfg.config.enabled) return false;
  startMonitor(
    projectDir,
    (lines) => {
      ctx.ui.setWidget(MONITOR_WIDGET_ID, lines, { placement: "belowEditor" });
    },
    { intervalMs: deps.monitorIntervalMs, readState: deps.readMonitorState }
  );
  return true;
}
function cmdRoadmap(ctx, projectDir) {
  const roadmap = readRoadmap(projectDir);
  if (!roadmap.ok) {
    ctx.ui.notify(`[autopilot] ${roadmap.error}`, "warning");
    return;
  }
  const lines = [];
  if (roadmap.stages.length === 0) lines.push("(no stages parsed)");
  for (const stage of roadmap.stages) {
    lines.push(`Stage ${stage.number}: ${stage.title} \u2014 ${stage.status}`);
    lines.push(`  goal: ${stage.goal === "" ? "(missing)" : stage.goal}`);
    const keys = stage.keys.map((k) => `${k.key}=${stage.keyStatus[k.key] ?? "-"}`).join(", ");
    lines.push(`  keys: ${keys === "" ? "(none)" : keys}`);
  }
  for (const w of roadmap.warnings) lines.push(`warning: ${w}`);
  ctx.ui.notify(lines.join("\n"), "info");
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts
import * as fs26 from "node:fs";
import * as path30 from "node:path";
var AckStore = class {
  constructor(agenticdocRoot2) {
    this.filePath = path30.join(agenticdocRoot2, "_workers.acked");
    this.lockPath = path30.join(agenticdocRoot2, "..", ".mw", "workers.lock");
  }
  /** taskKey -> ackedAt (UTC ISO). Missing file yields an empty map; `#`
   * comment lines and malformed rows are skipped. */
  readAll() {
    const result = /* @__PURE__ */ new Map();
    if (!fs26.existsSync(this.filePath)) return result;
    const lines = fs26.readFileSync(this.filePath, "utf8").split("\n");
    for (const line of lines) {
      const entry = parseAckLine(line);
      if (entry === void 0) continue;
      result.set(entry.taskKey, entry.ackedAt);
    }
    return result;
  }
  /** Ack taskKeys: hold the workers lock, read-merge-write via tmp + rename.
   * Idempotent — re-acking a key overwrites its timestamp. Returns the keys
   * actually written plus the keys rejected by taskKey validation (empty or
   * containing `|`); rejected keys never touch the file. */
  async ack(taskKeys) {
    const ackedAt = (/* @__PURE__ */ new Date()).toISOString();
    const acked = [];
    const rejected = [];
    for (const taskKey of taskKeys) {
      if (!isValidTaskKey(taskKey)) {
        rejected.push(taskKey);
      } else if (!acked.includes(taskKey)) {
        acked.push(taskKey);
      }
    }
    if (acked.length === 0) return { acked, rejected };
    const release = await acquireLock(this.lockPath);
    try {
      const merged = this.readAll();
      for (const taskKey of acked) {
        merged.set(taskKey, ackedAt);
      }
      const content = `${[...merged].map(([key, ts]) => `${key} | ${ts}`).join("\n")}
`;
      const tmpPath = `${this.filePath}.tmp`;
      fs26.writeFileSync(tmpPath, content, "utf8");
      fs26.renameSync(tmpPath, this.filePath);
    } finally {
      release();
    }
    return { acked, rejected };
  }
};
function parseAckLine(line) {
  const parts = line.split("|");
  if (parts.length !== 2) return void 0;
  const taskKey = (parts[0] ?? "").trim();
  const ackedAt = (parts[1] ?? "").trim();
  if (!taskKey || taskKey.startsWith("#") || !ackedAt) return void 0;
  return { taskKey, ackedAt };
}
function isValidTaskKey(taskKey) {
  return taskKey.length > 0 && !taskKey.includes("|") && taskKey.trim().length > 0;
}

// packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
var POLL_INTERVAL_MS = 4e3;
function isTerminal(status) {
  return status === "done" || status === "failed" || status === "needs-clarification";
}
function docWriteTarget(toolName, args, projectDir, agenticdocRoot2) {
  if (toolName !== "write" && toolName !== "edit") return void 0;
  const filePath = args?.path;
  if (typeof filePath !== "string" || filePath === "") return void 0;
  const rel = path31.relative(path31.resolve(agenticdocRoot2), path31.resolve(projectDir, filePath));
  if (rel.startsWith("..") || path31.isAbsolute(rel)) return void 0;
  const parts = rel.split(path31.sep);
  const doc = parts.length === 2 ? parts[1] : void 0;
  if (doc !== "spec.md" && doc !== "design.md" && doc !== "plan.md") return void 0;
  const key = parts[0] ?? "";
  if (!key || key.startsWith("_") || key.startsWith(".")) return void 0;
  return { key, doc };
}
function evidencePhaseFromWrite(toolName, args, projectDir, agenticdocRoot2) {
  if (toolName !== "write" && toolName !== "edit") return void 0;
  const filePath = args?.path;
  if (typeof filePath !== "string" || filePath === "") return void 0;
  const rel = path31.relative(path31.resolve(agenticdocRoot2), path31.resolve(projectDir, filePath));
  if (rel.startsWith("..") || path31.isAbsolute(rel)) return void 0;
  const parts = rel.split(path31.sep);
  if (parts.length !== 4 || parts[1] !== "evidence" || parts[2] !== "research") return void 0;
  const note = parts[3] ?? "";
  if (!note.endsWith(".md")) return void 0;
  const phase = note.startsWith("spec-") ? "spec" : note.startsWith("design-") ? "design" : void 0;
  if (!phase) return void 0;
  const key = parts[0] ?? "";
  if (!key || key.startsWith("_") || key.startsWith(".")) return void 0;
  return { key, phase };
}
function evidenceReviewNotice(ctx, key, phase, agenticdocRoot2, notified) {
  const dedup = `${key}:${phase}`;
  if (notified.has(dedup)) return;
  const docs = readPhaseDocs(agenticdocRoot2, key);
  const docOk = phase === "spec" ? docs.spec : docs.design;
  const evidence = phase === "spec" ? docs.specEvidence : docs.designEvidence;
  if (!docOk || evidence < 1) return;
  notified.add(dedup);
  const doc = phase === "spec" ? "spec.md" : "design.md";
  ctx.ui.notify(
    `[mw] ${key}: ${phase} \u9636\u6BB5\u8BC1\u636E\u5DF2\u5C31\u4F4D\uFF08${evidence} \u4EFD research note\uFF09\u2014\u2014\u5EFA\u8BAE\u5BF9\u7167 evidence/research/ \u590D\u67E5 ${doc}\uFF08\u65AD\u8A00-\u8BC1\u636E\u5BF9\u7167 / \u6570\u5B57\u53E3\u5F84 / \u5185\u90E8\u4E00\u81F4\u6027 / \u53EF\u8BC1\u4F2A\u6027\uFF09\u3002\u4F55\u65F6\u6267\u884C\u590D\u67E5\u7531\u4F60\u51B3\u5B9A\u3002`,
    "info"
  );
}
function nudgeGoalUnestablished(pi, agenticdocRoot2, hasUI) {
  const goal = readGoal(agenticdocRoot2);
  if (hasUI && !isGoalEstablished(goal)) {
    pi.sendUserMessage(
      "[agent-team-loop] \u9879\u76EE\u603B\u76EE\u6807\uFF08.agenticdoc/goal.md\uFF09\u5C1A\u672A\u786E\u7ACB\u3002\n\u5EFA\u8BAE\u5148\u8FD0\u884C /goal\uFF0C\u4E0E\u6211\u5BF9\u8BDD\u5171\u521B\u9879\u76EE\u603B\u76EE\u6807\u2014\u2014\u5B83\u662F\u540E\u7EED\u6BCF\u4E2A spec \u5BF9\u9F50\u7684\u951A\u70B9\u3002\n\uFF08\u4E5F\u53EF\u76F4\u63A5\u7F16\u8F91 .agenticdoc/goal.md \u586B\u597D\u4E09\u6BB5\u5185\u5BB9\u5E76\u628A status \u6539\u4E3A active\u3002\uFF09"
    );
  }
}
async function autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, key, doc, agenticdocRoot2, ctx) {
  const docs = readPhaseDocs(agenticdocRoot2, key);
  if (doc === "spec.md" && docs.specEvidence < 1) {
    ctx.ui.notify(
      `[mw] ${key}: no evidence/research/spec-*.md found \u2014 write the research notes (or a zero-research declaration) alongside the spec; the advance-to-design gate checks them.`,
      "warning"
    );
  }
  if (doc === "design.md" && docs.specEvidence < 1) {
    ctx.ui.notify(
      `[mw] ${key}: no evidence/research/spec-*.md found \u2014 the advance-to-design gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`,
      "warning"
    );
  }
  if (doc === "plan.md") {
    if (!docs.design) {
      ctx.ui.notify(
        `[mw] ${key}: design.md missing or under 500 bytes \u2014 required before plan (run the system-design workflow).`,
        "warning"
      );
    } else if (docs.designEvidence < 1) {
      ctx.ui.notify(
        `[mw] ${key}: no evidence/research/design-*.md found \u2014 the advance-to-plan gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`,
        "warning"
      );
    }
  }
  const row = indexStore.findByKey(key);
  const wasWatching = watch.key === key;
  const wasClaimed = row?.claimId === windowClaimId();
  if (wasWatching && wasClaimed) return;
  const result = await takeOverKey(indexStore, key, false, agenticdocRoot2);
  watch.key = key;
  pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: result.ok });
  refreshWatch(ctx);
  if (result.ok) {
    ctx.ui.notify(
      `[mw] claimed key '${key}' (doc write detected) \u2014 watching it${result.created ? " (new key registered)" : ""}.`,
      "info"
    );
    if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
  } else {
    ctx.ui.notify(
      `[mw] key '${key}' is claimed by another live window (${result.blockedBy}) \u2014 watching only.`,
      "warning"
    );
  }
}
async function restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot2, ctx) {
  let data;
  try {
    const entries = ctx.sessionManager.getEntries();
    for (let i = entries.length - 1; i >= 0; i--) {
      const e = entries[i];
      if (e.type === "custom" && e.customType === WATCH_ENTRY_TYPE) {
        data = e.data;
        break;
      }
    }
  } catch {
    return;
  }
  if (!data?.key) return;
  const key = data.key;
  watch.key = key;
  if (data.claimed) {
    const row = indexStore.findByKey(key);
    if (row) {
      const self = windowClaimId();
      if (claimState(row.claimId, self) === "held-live") {
        ctx.ui.notify(
          `[mw] key '${key}' is claimed by another window (${row.claimId}) \u2014 watching only.`,
          "warning"
        );
      } else {
        const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", {
          demoteOthers: false,
          activate: false
        });
        if (!outcome.ok) {
          ctx.ui.notify(
            `[mw] key '${key}' is claimed by another window (${outcome.blockedBy}) \u2014 watching only.`,
            "warning"
          );
        }
      }
    }
  }
  setWatchWidget(ctx, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot2, key));
  pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: data.claimed ?? false });
  const pmStatePath = path31.join(agenticdocRoot2, key, "pm-state.md");
  if (fs27.existsSync(pmStatePath)) {
    const updated = fs27.statSync(pmStatePath).mtime.toISOString();
    ctx.ui.notify(
      `[mw] key '${key}' \u6709\u5DF2\u4FDD\u5B58\u7684 pm-state.md\uFF08\u66F4\u65B0\u4E8E ${updated}\uFF09\u3002\u5982\u9700\u63A5\u7EED\u4E0A\u6B21\u7684\u5DE5\u4F5C\u4E0A\u4E0B\u6587\uFF0C\u8BA9 agent \u8BFB\u53D6 ${key}/pm-state.md \u7684 Notes \u533A\u3002`,
      "info"
    );
  }
}
function pickWorkerRoute(taskContent) {
  if (/^type:\s*codex/im.test(taskContent)) return { cli: "codex", provider: "" };
  return { cli: "pi", provider: "timi" };
}
function readModel(taskContent) {
  const m = taskContent.match(/^model:\s*(.+)$/im);
  return m ? m[1].trim() : "";
}
var ORIGIN_LINE_RE = /^origin:[ \t]*(\S+)[ \t\r]*$/m;
function readTaskOrigin(taskContent) {
  return ORIGIN_LINE_RE.exec(taskContent)?.[1];
}
function isConductorTask(taskMdPath) {
  try {
    return readTaskOrigin(fs27.readFileSync(taskMdPath, "utf8")) === "conductor";
  } catch {
    return false;
  }
}
async function dispatchNewTasks(workerStore, agenticdocRoot2, opts = {}) {
  if (!fs27.existsSync(agenticdocRoot2)) return;
  const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey));
  let owners;
  try {
    owners = fs27.readdirSync(agenticdocRoot2, { withFileTypes: true });
  } catch {
    return;
  }
  for (const owner of owners) {
    if (!owner.isDirectory() || owner.name.startsWith(".")) continue;
    const workersDir = path31.join(agenticdocRoot2, owner.name, "workers");
    let taskDirs;
    try {
      taskDirs = fs27.readdirSync(workersDir, { withFileTypes: true });
    } catch {
      continue;
    }
    const undispatched = [];
    for (const taskDir of taskDirs) {
      if (!taskDir.isDirectory() || taskDir.name.startsWith(".")) continue;
      const taskKey = taskDir.name;
      if (dispatched.has(taskKey)) continue;
      const taskMdPath = path31.join(workersDir, taskKey, "task.md");
      if (!fs27.existsSync(taskMdPath)) continue;
      if (isConductorTask(taskMdPath)) continue;
      undispatched.push({ taskKey, taskMdPath });
    }
    if (undispatched.length === 0) continue;
    if (owner.name !== SCRATCH_WORKERS_KEY) {
      const gaps = dispatchDocGaps(agenticdocRoot2, owner.name);
      if (gaps.length > 0) {
        if (!opts.warnedKeys?.has(owner.name)) {
          if (opts.onDocGate?.(owner.name, gaps) !== false) {
            opts.warnedKeys?.add(owner.name);
          }
        }
        continue;
      }
    }
    for (const { taskKey, taskMdPath } of undispatched) {
      const taskContent = fs27.readFileSync(taskMdPath, "utf8");
      const { cli, provider } = pickWorkerRoute(taskContent);
      const model = readModel(taskContent);
      try {
        await dispatchTask(
          {
            taskKey,
            status: "pending",
            cli,
            provider,
            model,
            taskPath: taskMdPath
          },
          workerStore
        );
      } catch (err) {
        console.error(`[mw] dispatch refused for ${taskKey}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
  }
}
var PM_CONTINUE_HINT = "[mw] worker \u7EC8\u6001\u56DE\u8BFB\u3002\u8BF7\u7EE7\u7EED PM \u5FAA\u73AF\uFF1A\u5438\u6536\u4E0A\u8FF0\u7ED3\u679C\uFF08done\u2192\u63A8\u8FDB\u4E0B\u4E00\u4EFB\u52A1/phase\uFF1Bfailed\u2192\u8BFB worker.log \u4E0E trace.log \u6392\u67E5\u540E\u51B3\u5B9A\u91CD\u8BD5\u6216\u4FEE\u590D\uFF1Bneeds-clarification\u2192\u6574\u7406\u95EE\u9898\u5411\u7528\u6237\u6F84\u6E05\uFF1B\u8D85\u65F6\u5931\u8D25\uFF08Exit Reason \u542B idle/wall timeout\uFF09\u2192 wall \u578B\u7528\u53CC\u500D timeout \u9884\u7B97\u91CD\u6D3E\u4E00\u6B21\uFF0C\u518D\u5931\u8D25\u8F6C PM \u76F4\u6267\uFF0Cidle \u578B\u76F4\u63A5\u6392\u67E5\u73AF\u5883\uFF09\uFF0C\u7136\u540E\u6D3E\u53D1\u4E0B\u4E00\u4E2A\u4EFB\u52A1\u6216\u6C47\u62A5\u9636\u6BB5\u5B8C\u6210\u3002\u5438\u6536\u7EC8\u6001\u7ED3\u679C\u540E\u8C03\u7528 ack_worker_result(task_key)\uFF08\u6216 /mw ack all\uFF09\u786E\u8BA4\u5904\u7406\u5B8C\u6210\uFF0Cwidget \u5F85\u5904\u7406\u533A\u624D\u4F1A\u6E05\u7A7A\u3002";
function heartbeatStatsSuffix(taskDir, entry) {
  const prog = readTaskProgress(taskDir);
  if (prog?.startTs && prog.endTs) {
    const durMs2 = Math.max(0, Date.parse(prog.endTs) - Date.parse(prog.startTs));
    const ph = prog.endPhases && prog.endPhases !== "-" ? `, ph ${prog.endPhases}` : "";
    return ` (${formatHeartbeatAge(durMs2)}${ph})`;
  }
  const hb = prog?.heartbeat;
  if (hb && hb.count >= 2) {
    const durMs2 = Math.max(0, Date.parse(hb.lastTs) - Date.parse(hb.firstTs));
    const ph = hb.phase === "-" ? "" : `, ph ${hb.phase}/${hb.phaseTotal}`;
    return ` (${formatHeartbeatAge(durMs2)}${ph})`;
  }
  const durMs = Date.parse(entry.updatedAt) - Date.parse(entry.dispatchedAt);
  if (!Number.isNaN(durMs) && durMs > 0) return ` (${formatHeartbeatAge(durMs)})`;
  return "";
}
function startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot2, watch, ui, pollIntervalMs = POLL_INTERVAL_MS) {
  const notified = new Set(
    workerStore.readAll().filter((e) => isTerminal(e.status)).map((e) => e.taskKey)
  );
  const escalated = /* @__PURE__ */ new Set();
  let widgetShown = false;
  return setInterval(() => {
    try {
      if (watch.key) {
        applyWatchWidget(ui, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot2, watch.key));
        widgetShown = true;
      } else if (widgetShown) {
        applyWatchWidget(ui, void 0);
        widgetShown = false;
      }
      const entries = workerStore.readAll();
      for (const entry of entries) {
        if (entry.status !== "running" || escalated.has(entry.taskKey)) continue;
        if (!watch.key || ownerKeyOf(entry, agenticdocRoot2) !== watch.key) continue;
        const ck = readTaskProgress(path31.dirname(entry.taskPath))?.checkpoint;
        if (!ck || ck.risk === "low") continue;
        escalated.add(entry.taskKey);
        const taskDir = path31.dirname(entry.taskPath);
        deliverPmAlert(
          pi,
          `[mw] \u53D1\u6563\u98CE\u9669\uFF1Aworker '${entry.taskKey}' \u68C0\u67E5\u70B9 risk=${ck.risk}\uFF08elapsed ${Math.round(ck.elapsedS / 60)}m\uFF0Creads=${ck.reads} writes=${ck.writes}\uFF0Cphases=${ck.phases}\uFF0C\u91CD\u590D\u8BFB top=${ck.repeatTop}\uFF09\u3002\u673A\u5668\u5224\u636E\u4EC5\u4F9B\u53C2\u8003\u2014\u2014\u8BF7\u7ED3\u5408\u672C key \u6700\u5168\u4E0A\u4E0B\u6587\u5224\u65AD\uFF1A\u7EE7\u7EED\u7B49\u5F85 / steer \u6536\u7A84\u8303\u56F4 / \u7EC8\u6B62\u5E76\u5206\u62C6\u91CD\u6D3E / PM \u76F4\u6267\u3002\u8BC1\u636E\uFF1A${path31.join(taskDir, "trace.log")}\uFF08[CHECKPOINT] \u884C\uFF09\u4E0E ${path31.join(taskDir, "progress.md")}\uFF08worker \u81EA\u8BC4\uFF09\u3002`
        );
      }
      for (const entry of entries) {
        if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
        notified.add(entry.taskKey);
        if (!watch.key || ownerKeyOf(entry, agenticdocRoot2) !== watch.key) continue;
        const taskDir = path31.dirname(entry.taskPath);
        const header = `[${entry.taskKey}] ${entry.status}${heartbeatStatsSuffix(taskDir, entry)}`;
        const body = readOutputBody(taskDir);
        if (body) {
          deliverWorkerResult(pi, `${header}:

${body}

${PM_CONTINUE_HINT}`);
        } else {
          const logPath = path31.join(taskDir, "worker.log");
          const spawnFailure = readSpawnFailure(taskDir);
          deliverWorkerResult(
            pi,
            `${header} \u2014 ${spawnFailure ? `${spawnFailure}\u3002\u65E5\u5FD7\uFF1A${logPath}` : `\u65E0 output.md \u6458\u8981\uFF08worker \u53EF\u80FD\u5D29\u6E83/\u8D85\u65F6\uFF09\u3002\u65E5\u5FD7\uFF1A${logPath}`}

${PM_CONTINUE_HINT}`
          );
        }
      }
    } catch {
    }
  }, pollIntervalMs);
}
var PARALLEL_PROTOCOL_MARKER = "[mw] \u5E76\u884C\u4F18\u5148\u534F\u8BAE";
var PARALLEL_PROTOCOL = [
  `${PARALLEL_PROTOCOL_MARKER}\uFF08PM \u5E38\u9A7B\u89C4\u5219\uFF09\uFF1A`,
  "1. \u62C6\u89E3\u4EFB\u4F55 phase\uFF08spec/design/plan/tasks\uFF09\u4E4B\u524D\uFF0C\u5148\u505A\u5E76\u884C\u6027\u5206\u6790\uFF1A\u53EF\u5E76\u884C\u5355\u5143 / \u5171\u4EAB\u8D44\u6E90\u4E0E\u6587\u4EF6\u51B2\u7A81\u9762 / \u5FC5\u987B\u4E32\u884C\u7684\u7406\u7531\u3002",
  "2. spec/design \u7684\u8C03\u7814\u4E0E\u8BC1\u636E\u6536\u96C6\u9ED8\u8BA4\u5168\u5E76\u884C\uFF1A\u628A\u8C03\u7814\u62C6\u6210\u4E92\u4E0D\u91CD\u53E0\u7684\u7814\u7A76\u95EE\u9898 RQ-1..N\uFF0C\u4E00\u6B21\u6027\u6D3E\u53D1 N \u4E2A type: research worker",
  "   \uFF08\u53EA\u8BFB\u89D2\u8272\uFF0C\u5F7C\u6B64\u65E0\u6587\u4EF6\u51B2\u7A81\uFF09\uFF0C\u6BCF\u4E2A RQ \u53EA\u5199\u552F\u4E00\u7684 evidence/research/<phase>-<rq-slug>-<date>.md\uFF1B\u7981\u6B62\u4E24\u4E2A worker \u5199\u540C\u4E00\u6587\u4EF6\u3002",
  "3. \u7F16\u7801\u6309\u6587\u4EF6/\u6A21\u5757\u8FB9\u754C\u5E76\u884C\uFF1A\u540C\u4E00\u6587\u4EF6\u540C\u4E00\u65F6\u523B\u53EA\u5141\u8BB8\u4E00\u4E2A worker\u3002",
  "4. \u76F8\u4F4D\u6587\u6863\uFF08spec.md / design.md\uFF09\u7531 PM \u81EA\u5DF1\u4E32\u884C\u5199\uFF0C\u4E0D\u6D3E worker\u3002",
  "5. \u6D3E\u53D1\u524D\u5148\u770B widget \u4E0A\u7684 running worker \u6570\uFF1A\u80FD\u5E76\u884C\u5C31\u4E0D\u8981\u4E32\u884C\u7B49\u5F85\uFF1Bworker \u7EC8\u6001\u56DE\u8BFB\u540E\u7ACB\u523B\u8865\u6D3E\u4E0B\u4E00\u6279\u3002"
].join("\n");
function pmActivate(pi) {
  const projectDir = process.cwd();
  const agenticdocRoot2 = agenticdocRoot(projectDir);
  const workerStore = new WorkerStore(agenticdocRoot2);
  const ackStore = new AckStore(agenticdocRoot2);
  const indexStore = new IndexStore(agenticdocRoot2);
  const watch = { key: void 0 };
  const ui = { ctx: void 0 };
  const refreshWatch = (ctx) => {
    if (!watch.key) {
      setWatchWidget(ctx, void 0);
      return;
    }
    setWatchWidget(ctx, renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot2, watch.key));
  };
  registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot2);
  registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot2);
  registerMwCommands(pi, projectDir, workerStore, ackStore);
  registerMwTools(pi, projectDir);
  registerAdvancePhaseTool(pi, projectDir);
  registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot2, watch, projectDir);
  registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot2);
  registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot2, watch, projectDir);
  try {
    registerRagTools(pi, projectDir);
  } catch (err) {
    console.error(`[mw] rag tools disabled: ${err instanceof Error ? err.message : String(err)}`);
  }
  registerWatchCommand(pi, watch, refreshWatch, indexStore);
  registerAutopilotCommands(pi, projectDir);
  registerMainWindowModel(pi);
  registerPmStateGuard(pi, projectDir, agenticdocRoot2);
  pi.on("before_agent_start", (event) => {
    const base = typeof event.systemPrompt === "string" ? event.systemPrompt : "";
    if (base.includes(PARALLEL_PROTOCOL_MARKER)) return void 0;
    return { systemPrompt: base === "" ? PARALLEL_PROTOCOL : `${base}

${PARALLEL_PROTOCOL}` };
  });
  const pollHandle = startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot2, watch, ui);
  pi.on("session_shutdown", () => clearInterval(pollHandle));
  const docGateWarned = /* @__PURE__ */ new Set();
  pi.on("agent_settled", () => {
    dispatchNewTasks(workerStore, agenticdocRoot2, {
      warnedKeys: docGateWarned,
      onDocGate: makeScopedDocGateNotifier(pi, watch)
    }).catch(() => {
    });
  });
  const pendingToolArgs = /* @__PURE__ */ new Map();
  pi.on("tool_execution_start", (event) => {
    if (event.toolName === "write" || event.toolName === "edit") {
      pendingToolArgs.set(event.toolCallId, { toolName: event.toolName, args: event.args });
    }
  });
  const evidenceReviewNotified = /* @__PURE__ */ new Set();
  pi.on("tool_execution_end", (event, ctx) => {
    const pending = pendingToolArgs.get(event.toolCallId);
    pendingToolArgs.delete(event.toolCallId);
    if (!pending || event.isError) return;
    const target = docWriteTarget(pending.toolName, pending.args, projectDir, agenticdocRoot2);
    if (target) {
      autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, target.key, target.doc, agenticdocRoot2, ctx).catch(
        () => {
        }
      );
      if (target.doc !== "plan.md") {
        evidenceReviewNotice(
          ctx,
          target.key,
          target.doc === "spec.md" ? "spec" : "design",
          agenticdocRoot2,
          evidenceReviewNotified
        );
      }
      return;
    }
    const ev = evidencePhaseFromWrite(pending.toolName, pending.args, projectDir, agenticdocRoot2);
    if (ev) {
      evidenceReviewNotice(ctx, ev.key, ev.phase, agenticdocRoot2, evidenceReviewNotified);
    }
  });
  pi.on("session_start", async (_event, ctx) => {
    ui.ctx = ctx;
    autoStartMonitor(ctx, projectDir);
    await restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot2, ctx);
    const initialized = fs27.existsSync(path31.join(projectDir, ".agenticdoc"));
    if (!initialized) {
      const result = initMw(projectDir);
      if (result.ok) {
        displaySummary(pi, "[mw] Project initialized \u2014 .agenticdoc/ .mw/ .pi/extensions/ created.");
      } else {
        displaySummary(pi, `[mw] Init failed: ${result.error}`);
        return;
      }
    }
    const mwStatus = getMwStatus(projectDir);
    if (!mwStatus.running) {
      const started = startMw(projectDir);
      if (started) {
        const confirmed = await waitForMwStart(projectDir, 8e3);
        displaySummary(
          pi,
          confirmed ? "[mw] Background service started." : "[mw] Background service \u542F\u52A8\u672A\u786E\u8BA4\uFF08\u53EF\u80FD\u9884\u68C0\u5931\u8D25\u6216\u4ECD\u5728\u542F\u52A8\uFF09\u2014\u2014\u8FD0\u884C /mw doctor \u8BCA\u65AD\u3002"
        );
      } else {
        displaySummary(pi, "[mw] Could not find mw.py \u2014 run `mw start --project=.` manually.");
      }
    } else {
      const stale = serveStaleness(projectDir);
      if (stale?.stale) {
        displaySummary(
          pi,
          `[mw] serve (PID ${mwStatus.pid}) is running stale code \u2014 ${stale.detail}. Run /mw restart.`
        );
      }
    }
    nudgeGoalUnestablished(pi, agenticdocRoot2, ctx.hasUI);
  });
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts
import * as fs28 from "node:fs";
import * as os4 from "node:os";
import * as path32 from "node:path";
var IS_WIN322 = process.platform === "win32";
var ENV_GATE_ROOT = "MW_IMPL_GATE_ROOT";
var ENV_WORKER_TASK = "PI_WORKER_TASK";
var AGENTICDOC_DIR2 = ".agenticdoc";
var INDEX_FILE = "_index.parallel";
var MINI_SPEC_FILE = "mini-spec.md";
var GATE_LOG_FILE = "_impl_gate.log";
var MINI_SPEC_FRESH_MS = 24 * 60 * 60 * 1e3;
var PACKAGES_DIR = "packages";
var CODE_EXTENSIONS = [".ts", ".tsx", ".js", ".cjs", ".mjs", ".py"];
var CODE_EXCLUDED_SEGMENTS = ["node_modules", "dist", ".tmp"];
var WRITE_VERBS = /* @__PURE__ */ new Set(["tee", "cp", "mv", "rm", "sed"]);
var GATE_EXPLANATION = "Create a key first: run /agentic (the AgenticTask flow), or write .agenticdoc/<key>/spec.md \u2014 update_index.py claim then records this window (host:pid) as the owner. For a trivial fix use the mini fast path: write .agenticdoc/<key>/mini-spec.md, then retry this tool call (the pass is audited to .agenticdoc/_impl_gate.log).";
function fold(p) {
  return IS_WIN322 ? p.toLowerCase() : p;
}
function toForwardSlashes(p) {
  return p.replaceAll("\\", "/");
}
function expandTildePath(p) {
  if (p === "~") return os4.homedir();
  if (p.startsWith("~/") || p.startsWith("~\\")) {
    return path32.join(os4.homedir(), p.slice(2));
  }
  return p;
}
function isExistingDir(absPath) {
  try {
    return fs28.statSync(absPath).isDirectory();
  } catch {
    return false;
  }
}
function defaultReadTextFile(absPath) {
  try {
    return fs28.readFileSync(absPath, "utf8");
  } catch {
    return void 0;
  }
}
function resolveGateRoot(env = process.env) {
  const raw = env[ENV_GATE_ROOT];
  if (typeof raw === "string" && raw !== "") {
    return path32.resolve(expandTildePath(raw));
  }
  return process.cwd();
}
function currentClaimId() {
  return `${os4.hostname()}:${process.pid}`;
}
function codePathRel(absPath, root) {
  const target = toForwardSlashes(fold(path32.normalize(absPath)));
  const prefix = `${toForwardSlashes(fold(path32.normalize(root)))}/${PACKAGES_DIR}/`;
  if (!target.startsWith(prefix)) return void 0;
  return target.slice(prefix.length);
}
function isCodePathAbs(absPath, root) {
  const rel = codePathRel(absPath, root);
  if (rel === void 0 || rel === "") return false;
  const ext2 = path32.extname(rel).toLowerCase();
  if (!CODE_EXTENSIONS.includes(ext2)) return false;
  const segments = rel.split("/");
  return !segments.some((s) => CODE_EXCLUDED_SEGMENTS.includes(s));
}
function isCodePath(rawPath, root = resolveGateRoot(), cwd = process.cwd()) {
  if (typeof rawPath !== "string" || rawPath === "") return false;
  return isCodePathAbs(path32.resolve(cwd, expandTildePath(rawPath)), root);
}
function splitTableRow2(line) {
  let cells = line.split("|").map((c) => c.trim());
  if (cells.length > 0 && cells[0] === "") cells = cells.slice(1);
  if (cells.length > 0 && cells[cells.length - 1] === "") cells = cells.slice(0, -1);
  return cells;
}
function isSeparatorRow(cells) {
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}
function parseIndexRows(content) {
  let header;
  const dataRows = [];
  for (const line of content.split(/\r?\n/)) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    const cells = splitTableRow2(t);
    if (header === void 0) {
      if (!isSeparatorRow(cells)) header = cells;
    } else if (!isSeparatorRow(cells)) {
      dataRows.push(cells);
    }
  }
  if (header === void 0) return void 0;
  const keyIdx = header.findIndex((c) => c.toLowerCase() === "key");
  const statusIdx = header.findIndex((c) => c.toLowerCase() === "status");
  const claimIdx = header.findIndex((c) => c.toLowerCase() === "claimid");
  if (keyIdx < 0 || statusIdx < 0 || claimIdx < 0) return void 0;
  return dataRows.map((cells) => ({
    key: cells[keyIdx] ?? "",
    status: cells[statusIdx] ?? "",
    claimId: cells[claimIdx] ?? ""
  }));
}
function hasActiveKeyClaim(root, claimId, readIndexFile = defaultReadTextFile) {
  const wanted = claimId.trim().toLowerCase();
  if (wanted === "") return false;
  const content = readIndexFile(path32.join(root, AGENTICDOC_DIR2, INDEX_FILE));
  if (content === void 0) return false;
  const rows = parseIndexRows(content);
  if (rows === void 0) return false;
  return rows.some((r) => r.status.toLowerCase() === "active" && r.claimId.toLowerCase() === wanted);
}
function findFreshMiniSpec(root, now = Date.now(), maxAgeMs = MINI_SPEC_FRESH_MS) {
  let entries;
  try {
    entries = fs28.readdirSync(path32.join(root, AGENTICDOC_DIR2), { withFileTypes: true });
  } catch {
    return void 0;
  }
  let best;
  let bestMtime = Number.NEGATIVE_INFINITY;
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
    const candidate = path32.join(root, AGENTICDOC_DIR2, entry.name, MINI_SPEC_FILE);
    try {
      const mtime = fs28.statSync(candidate).mtimeMs;
      if (now - mtime <= maxAgeMs && mtime > bestMtime) {
        best = candidate;
        bestMtime = mtime;
      }
    } catch {
    }
  }
  return best;
}
function readHeredocDelimiter(command, start) {
  let i = start;
  const n = command.length;
  if (command[i] === "-") i += 1;
  while (command[i] === " " || command[i] === "	") i += 1;
  let delim = "";
  if (command[i] === "'" || command[i] === '"') {
    const quote = command[i];
    i += 1;
    while (i < n && command[i] !== quote) {
      delim += command[i];
      i += 1;
    }
    if (i < n) i += 1;
  } else {
    while (i < n && !/[\s;&|<>()]/.test(command[i] ?? "")) {
      delim += command[i];
      i += 1;
    }
  }
  return { delim, next: i };
}
function skipHeredocBody(command, start, delim) {
  let i = start;
  const n = command.length;
  while (i < n) {
    i += 1;
    let line = "";
    while (i < n && command[i] !== "\n") {
      line += command[i];
      i += 1;
    }
    if (line.trim() === delim) return i;
  }
  return i;
}
var BACKSLASH_ESCAPES_UNQUOTED = /* @__PURE__ */ new Set([
  " ",
  "	",
  "\r",
  "\n",
  ";",
  "&",
  "|",
  "<",
  ">",
  "(",
  ")",
  "'",
  '"',
  "\\",
  "$",
  "`"
]);
var BACKSLASH_ESCAPES_DOUBLE_QUOTED = /* @__PURE__ */ new Set(["$", "`", '"', "\\", "\n"]);
function parseBashSegments(command) {
  const segments = [];
  let current = { words: [], redirectTargets: [] };
  let word = "";
  let hasWord = false;
  let quote = null;
  let pendingRedirect = false;
  let pendingRead = false;
  let heredocDelim;
  const flushWord = () => {
    if (!hasWord) return;
    if (pendingRedirect) {
      current.redirectTargets.push(word);
    } else if (!pendingRead) {
      current.words.push(word);
    }
    pendingRedirect = false;
    pendingRead = false;
    word = "";
    hasWord = false;
  };
  const endSegment = () => {
    flushWord();
    pendingRedirect = false;
    pendingRead = false;
    if (current.words.length > 0 || current.redirectTargets.length > 0) segments.push(current);
    current = { words: [], redirectTargets: [] };
  };
  let i = 0;
  const n = command.length;
  while (i < n) {
    const c = command[i] ?? "";
    if (quote !== null) {
      if (c === "\\" && quote === '"') {
        const next = command[i + 1];
        if (next !== void 0 && BACKSLASH_ESCAPES_DOUBLE_QUOTED.has(next)) {
          word += next;
          hasWord = true;
          i += 2;
        } else {
          word += c;
          hasWord = true;
          i += 1;
        }
        continue;
      }
      if (c === quote) {
        quote = null;
        i += 1;
        continue;
      }
      word += c;
      hasWord = true;
      i += 1;
      continue;
    }
    if (c === "'" || c === '"') {
      quote = c;
      hasWord = true;
      i += 1;
      continue;
    }
    if (c === "\\") {
      const next = command[i + 1];
      if (next !== void 0 && BACKSLASH_ESCAPES_UNQUOTED.has(next)) {
        word += next;
        hasWord = true;
        i += 2;
      } else {
        word += c;
        hasWord = true;
        i += 1;
      }
      continue;
    }
    if (c === " " || c === "	" || c === "\r") {
      flushWord();
      i += 1;
      continue;
    }
    if (c === "\n") {
      flushWord();
      if (heredocDelim !== void 0) {
        i = skipHeredocBody(command, i, heredocDelim);
        heredocDelim = void 0;
        continue;
      }
      i += 1;
      continue;
    }
    if (c === ";") {
      endSegment();
      i += 1;
      continue;
    }
    if (c === "&") {
      if (command[i + 1] === "&") {
        endSegment();
        i += 2;
        continue;
      }
      if (command[i + 1] === ">") {
        flushWord();
        pendingRedirect = true;
        i += 2;
        continue;
      }
      endSegment();
      i += 1;
      continue;
    }
    if (c === "|") {
      endSegment();
      i += command[i + 1] === "|" ? 2 : 1;
      continue;
    }
    if (c === "(" || c === ")") {
      endSegment();
      i += 1;
      continue;
    }
    if (c === "<") {
      if (command[i + 1] === "<") {
        flushWord();
        const parsed = readHeredocDelimiter(command, i + 2);
        heredocDelim = parsed.delim === "" ? void 0 : parsed.delim;
        i = parsed.next;
        continue;
      }
      flushWord();
      pendingRead = true;
      i += 1;
      continue;
    }
    if (c === ">") {
      if (hasWord && /^\d+$/.test(word)) {
        word = "";
        hasWord = false;
      } else {
        flushWord();
      }
      pendingRedirect = true;
      i += command[i + 1] === ">" ? 2 : 1;
      continue;
    }
    word += c;
    hasWord = true;
    i += 1;
  }
  flushWord();
  if (current.words.length > 0 || current.redirectTargets.length > 0) segments.push(current);
  return segments;
}
function stripEnvAssignments(words) {
  let i = 0;
  while (i < words.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i] ?? "")) i += 1;
  return words.slice(i);
}
function resolveToken(dir, token) {
  return path32.resolve(dir, expandTildePath(token));
}
function joinDestName(dest, src) {
  return path32.join(dest, path32.basename(expandTildePath(src)));
}
function verbTargets(verb, args, dir) {
  const operands = [];
  let targetDirOpt;
  let sedInPlace = false;
  let sedScriptOpt = false;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i] ?? "";
    if (arg === "--") {
      for (let j = i + 1; j < args.length; j++) operands.push(args[j] ?? "");
      break;
    }
    if (arg.startsWith("-") && arg !== "-" && arg !== "") {
      if ((verb === "cp" || verb === "mv") && (arg === "-t" || arg === "--target-directory")) {
        targetDirOpt = args[i + 1];
        i += 1;
      } else if ((verb === "cp" || verb === "mv") && arg.startsWith("--target-directory=")) {
        targetDirOpt = arg.slice("--target-directory=".length);
      } else if (verb === "sed" && (/^-i(\..+)?$/.test(arg) || arg === "--in-place" || arg.startsWith("--in-place="))) {
        sedInPlace = true;
      } else if (verb === "sed" && (arg === "-e" || arg === "-f" || arg === "--expression" || arg === "--file" || arg === "--script")) {
        sedScriptOpt = true;
        i += 1;
      } else if (verb === "sed" && (arg.startsWith("--expression=") || arg.startsWith("--file=") || arg.startsWith("--script="))) {
        sedScriptOpt = true;
      }
      continue;
    }
    operands.push(arg);
  }
  switch (verb) {
    case "tee":
    case "rm":
      return operands;
    case "cp":
    case "mv": {
      if (operands.length === 0) return [];
      if (targetDirOpt !== void 0) {
        return operands.map((src) => joinDestName(targetDirOpt ?? "", src));
      }
      if (operands.length < 2) return [];
      const dest = operands[operands.length - 1] ?? "";
      const srcs = operands.slice(0, -1);
      if (dest.endsWith("/") || dest.endsWith("\\") || isExistingDir(resolveToken(dir, dest))) {
        return srcs.map((src) => joinDestName(dest, src));
      }
      return [dest];
    }
    case "sed": {
      if (!sedInPlace) return [];
      return sedScriptOpt ? operands : operands.slice(1);
    }
    default:
      return [];
  }
}
function checkBashWriteTarget(command, root = resolveGateRoot(), cwd = process.cwd()) {
  if (typeof command !== "string" || command === "") return [];
  const hits = [];
  let dir = cwd;
  for (const segment of parseBashSegments(command)) {
    const argv = stripEnvAssignments(segment.words);
    const verb = argv.length > 0 ? path32.basename(argv[0] ?? "") : "";
    if (verb === "cd" && argv.length === 2) {
      dir = resolveToken(dir, argv[1] ?? "");
      continue;
    }
    for (const target of segment.redirectTargets) {
      if (isCodePathAbs(resolveToken(dir, target), root)) hits.push(target);
    }
    if (argv.length > 0 && WRITE_VERBS.has(verb)) {
      for (const target of verbTargets(verb, argv.slice(1), dir)) {
        if (isCodePathAbs(resolveToken(dir, target), root)) hits.push(target);
      }
    }
  }
  return hits;
}
function miniSpecBasis(mini, root) {
  const rel = path32.relative(root, mini);
  const shown = rel === "" || rel.startsWith("..") ? mini : rel;
  return `mini-spec:${toForwardSlashes(shown)}`;
}
function blockReason(toolName, targets, root) {
  const targetsText = targets.length === 1 ? targets[0] ?? "" : targets.join(", ");
  return `implementation-gate: blocked ${toolName} targeting code path ${targetsText}: this window holds no active AgenticTask key claim (no status=active row in ${AGENTICDOC_DIR2}/${INDEX_FILE} matches claim id ${currentClaimId()}), ${ENV_WORKER_TASK} is not set, and no ${AGENTICDOC_DIR2}/*/mini-spec.md is newer than 24h (root: ${root}). ${GATE_EXPLANATION}`;
}
function gateDecision(toolName, input, env, cwd = process.cwd()) {
  if (toolName !== "write" && toolName !== "edit" && toolName !== "bash") {
    return { blocked: false, basis: "not-gated-tool" };
  }
  const root = resolveGateRoot(env);
  let targets;
  if (toolName === "bash") {
    const command = input.command;
    if (typeof command !== "string" || command === "") {
      return { blocked: false, basis: "no-command" };
    }
    targets = checkBashWriteTarget(command, root, cwd);
    if (targets.length === 0) return { blocked: false, basis: "no-code-path-target" };
  } else {
    const rawPath = input.path;
    if (typeof rawPath !== "string" || rawPath === "") {
      return { blocked: false, basis: "no-path" };
    }
    if (!isCodePath(rawPath, root, cwd)) return { blocked: false, basis: "not-a-code-path" };
    targets = [rawPath];
  }
  if (hasActiveKeyClaim(root, currentClaimId())) {
    return { blocked: false, basis: "claim", target: targets[0] };
  }
  const workerTask = env[ENV_WORKER_TASK];
  if (typeof workerTask === "string" && workerTask !== "") {
    return { blocked: false, basis: "worker-env", target: targets[0] };
  }
  const mini = findFreshMiniSpec(root);
  if (mini !== void 0) {
    return { blocked: false, basis: miniSpecBasis(mini, root), target: targets[0] };
  }
  return {
    blocked: true,
    reason: blockReason(toolName, targets, root),
    basis: "no-claim-no-mini",
    target: targets[0]
  };
}
function recordImplGateAudit(tag, toolName, target, basis, root = resolveGateRoot()) {
  try {
    const dir = path32.join(root, AGENTICDOC_DIR2);
    fs28.mkdirSync(dir, { recursive: true });
    fs28.appendFileSync(
      path32.join(dir, GATE_LOG_FILE),
      `[GATE] ${(/* @__PURE__ */ new Date()).toISOString()} ${tag} tool=${toolName} target=${target} basis=${basis}
`,
      "utf8"
    );
  } catch {
  }
}
function registerImplementationGate(pi) {
  pi.on("tool_call", (event) => {
    if (event.toolName !== "write" && event.toolName !== "edit" && event.toolName !== "bash") {
      return void 0;
    }
    const decision = gateDecision(event.toolName, event.input, process.env);
    if (decision.blocked) {
      recordImplGateAudit("blocked", event.toolName, decision.target ?? "", decision.basis);
      return { block: true, reason: decision.reason };
    }
    if (decision.basis.startsWith("mini-spec")) {
      recordImplGateAudit("mini-pass", event.toolName, decision.target ?? "", decision.basis);
    }
    return void 0;
  });
}

// packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts
import * as fs29 from "node:fs";
import * as os5 from "node:os";
import * as path33 from "node:path";
var IS_WIN323 = process.platform === "win32";
var PROTECTED_CONFIG_FILES = ["auth.json", "models.json", "settings.json", "oauth.json"];
var ENV_AGENT_DIR2 = "PI_CODING_AGENT_DIR";
var GUARD_EXPLANATION = "~/.pi/agent/{auth,models,settings,oauth}.json are cross-window config shared by every live pi session (credentials hot-reload per window). Modifying them from a running session breaks the other windows (2026-09-15 incident: clearing auth.json broke every open window with 'Provider is not configured'). Reads are allowed. To change credentials/models/settings: close pi windows and edit from a plain terminal, or use pi /login (core flow, outside the tool layer).";
function fold2(p) {
  return IS_WIN323 ? p.toLowerCase() : p;
}
function toForwardSlashes2(p) {
  return p.replaceAll("\\", "/");
}
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function boundary() {
  return "(?![\\w-])";
}
function fragmentPresent(scan, frag) {
  return new RegExp(escapeRegExp(frag) + boundary()).test(scan);
}
function expandTildePath2(p) {
  if (p === "~") return os5.homedir();
  if (p.startsWith("~/") || p.startsWith("~\\")) {
    return path33.join(os5.homedir(), p.slice(2));
  }
  return p;
}
function resolveAgentDir(env = process.env) {
  const raw = env[ENV_AGENT_DIR2];
  if (typeof raw === "string" && raw !== "") {
    return path33.resolve(expandTildePath2(raw));
  }
  return path33.join(os5.homedir(), ".pi", "agent");
}
function protectedConfigPaths(agentDir) {
  return PROTECTED_CONFIG_FILES.map((name) => path33.join(agentDir, name));
}
function isProtectedConfigPath(agentDir, rawPath, cwd = process.cwd()) {
  if (typeof rawPath !== "string" || rawPath === "") return false;
  const target = fold2(path33.normalize(path33.resolve(cwd, expandTildePath2(rawPath))));
  if (target === fold2(path33.normalize(agentDir))) return true;
  return protectedConfigPaths(agentDir).some((p) => target === fold2(path33.normalize(p)));
}
function expandCommandReferences(command, agentDir) {
  const home = os5.homedir();
  let s = command;
  for (const v of ["$HOME", `\${HOME}`, "%USERPROFILE%", "$env:USERPROFILE", "$Env:USERPROFILE"]) {
    s = s.split(v).join(home);
  }
  for (const v of [`$${ENV_AGENT_DIR2}`, `\${${ENV_AGENT_DIR2}}`, `%${ENV_AGENT_DIR2}%`]) {
    s = s.split(v).join(agentDir);
  }
  s = s.replace(/(^|[\s;&|(='"])~/g, (_m, prefix) => prefix + home);
  return s;
}
function bashScanText(command, agentDir) {
  return toForwardSlashes2(fold2(expandCommandReferences(command, agentDir)));
}
function protectedReferences(scan, agentDir) {
  const homeFrag = `${toForwardSlashes2(fold2(os5.homedir()))}/.pi/agent`;
  const dirFrag = toForwardSlashes2(fold2(path33.normalize(agentDir)));
  const refs = [];
  if (fragmentPresent(scan, homeFrag)) refs.push(homeFrag);
  if (dirFrag !== homeFrag && fragmentPresent(scan, dirFrag)) refs.push(dirFrag);
  const homeAbs = toForwardSlashes2(fold2(os5.homedir()));
  const cdHome = new RegExp(`(?:^|[\\s;&|(])cd\\s+["']?${escapeRegExp(homeAbs)}["']?${boundary()}`);
  if (cdHome.test(scan) && fragmentPresent(scan, ".pi/agent")) {
    refs.push(`${homeFrag} (relative after cd ~)`);
  }
  return refs;
}
var WRITE_VERB_RE = /\b(rm|rmdir|rd|del|erase|mv|move|ren|rename|cp|copy|rsync|install|dd|tee|shred|truncate|touch|chmod|chown|ln)\b/i;
var POWERSHELL_WRITE_RE = /\b(remove-item|move-item|copy-item|rename-item|new-item|set-content|add-content|clear-content|out-file)\b/i;
var SED_IN_PLACE_RE = /\bsed\b[^\n;&|]*(?:\s-i(?:\.\w+)?\b|--in-place\b)/i;
var FIND_WRITE_RE = /\bfind\b[^\n;&|]*(\s-delete\b|\s-exec\b|\s-execdir\b)/i;
var REDIRECT_RE = /(?:^|[\s;&|(])\d?>{1,2}\s*("[^"]*"|'[^']*'|[^\s;&|>]+)/g;
var INLINE_CODE_RE = /\b(python3?|node)\b[^\n;&|]*(\s-c\b|\s-e\b|\s--eval\b|<<)/i;
var INLINE_WRITE_MARKER_RE = /(['"][wa]['"]|writefile|write_file|unlink|rmsync|rmtree|os\.remove|os\.rename|shutil\.(move|copy|copyfile)|truncate\(|appendfile|open\([^)]*,\s*['"][wa]['"])/i;
function checkProtectedBashCommand(agentDir, command) {
  if (typeof command !== "string" || command === "") return { prohibited: false };
  const scan = bashScanText(command, agentDir);
  const refs = protectedReferences(scan, agentDir);
  const inline = INLINE_CODE_RE.test(scan) && INLINE_WRITE_MARKER_RE.test(scan);
  const bareFragment = new RegExp(escapeRegExp(".pi/agent") + boundary()).test(scan);
  if (refs.length === 0 && !(inline && bareFragment)) return { prohibited: false };
  const constructs = [];
  if (WRITE_VERB_RE.test(scan)) constructs.push("write verb");
  if (POWERSHELL_WRITE_RE.test(scan)) constructs.push("powershell write cmdlet");
  if (SED_IN_PLACE_RE.test(scan)) constructs.push("sed -i");
  if (FIND_WRITE_RE.test(scan)) constructs.push("find -delete/-exec");
  for (const m of scan.matchAll(REDIRECT_RE)) {
    const target = (m[1] ?? "").replace(/^["']|["']$/g, "");
    if (target !== "" && protectedReferences(target, agentDir).length > 0) constructs.push("redirect target");
  }
  if (inline) constructs.push("inline code write");
  if (constructs.length === 0) return { prohibited: false };
  const refText = refs.length > 0 ? refs.join(", ") : ".pi/agent (path assembled inside inline code)";
  return {
    prohibited: true,
    reason: `protected-config: blocked a bash command referencing cross-window config (${refText}) with a write construct (${constructs.join(", ")}). ${GUARD_EXPLANATION}`
  };
}
function recordProtectedBlockTrace(toolName, detail, taskPathEnv = process.env.PI_WORKER_TASK) {
  if (!taskPathEnv) return;
  try {
    const dir = path33.dirname(path33.resolve(taskPathEnv));
    fs29.mkdirSync(dir, { recursive: true });
    const first = detail.split("\n")[0] ?? "";
    fs29.appendFileSync(
      path33.join(dir, "trace.log"),
      `[PROTECTED_CONFIG] ${(/* @__PURE__ */ new Date()).toISOString()} blocked tool=${toolName} target=${first}
`,
      "utf8"
    );
  } catch {
  }
}
function registerProtectedConfigGuard(pi) {
  const agentDir = resolveAgentDir();
  pi.on("tool_call", (event) => {
    if (event.toolName === "write" || event.toolName === "edit") {
      const rawPath = event.input.path;
      if (typeof rawPath === "string" && rawPath !== "" && isProtectedConfigPath(agentDir, rawPath)) {
        recordProtectedBlockTrace(event.toolName, rawPath);
        return {
          block: true,
          reason: `protected-config: blocked ${event.toolName} of ${rawPath}. ${GUARD_EXPLANATION}`
        };
      }
      return void 0;
    }
    if (event.toolName === "bash") {
      const command = event.input.command;
      if (typeof command === "string" && command !== "") {
        const verdict = checkProtectedBashCommand(agentDir, command);
        if (verdict.prohibited) {
          recordProtectedBlockTrace(event.toolName, command);
          return { block: true, reason: verdict.reason };
        }
      }
      return void 0;
    }
    return void 0;
  });
}

// packages/coding-agent/src/extensions/agent-team-loop/index.ts
var ACTIVATION_FLAG = "__agentTeamLoopActivated";
async function activate(pi) {
  const g = globalThis;
  pi.on("session_shutdown", () => {
    delete g[ACTIVATION_FLAG];
  });
  if (g[ACTIVATION_FLAG]) {
    return;
  }
  g[ACTIVATION_FLAG] = true;
  registerProtectedConfigGuard(pi);
  registerImplementationGate(pi);
  if (process.env.PI_WORKER_TASK) {
    await workerModeActivate(pi);
  } else {
    pmActivate(pi);
  }
}
var index_default = activate;
export {
  activate,
  index_default as default
};
