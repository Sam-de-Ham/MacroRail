// A 3D relief of a preview stack: its depth map as a height field, the stack laid over it.
// Plain WebGL 2, drawn only when something changes. Drag turns it, a pinch or the wheel
// zooms, a double click resets the view.

const GRID = 240; // vertices across; rows follow the image's aspect
const FOV = (35 * Math.PI) / 180;
const MAX_TILT = (80 * Math.PI) / 180;

const VERTEX = `#version 300 es
in vec3 vertex; // u, v, depth (1 at the first shot)
uniform mat4 view, projection;
uniform float aspect, relief;
out vec2 uv;
out vec3 position;
void main() {
  uv = vertex.xy;
  vec4 p = view * vec4(vertex.x - 0.5, (0.5 - vertex.y) * aspect, (vertex.z - 0.5) * relief, 1.0);
  position = p.xyz;
  gl_Position = projection * p;
}`;

const FRAGMENT = `#version 300 es
precision mediump float;
in vec2 uv;
in vec3 position;
uniform sampler2D image;
out vec4 colour;
void main() {
  vec3 normal = normalize(cross(dFdx(position), dFdy(position)));
  float light = 0.6 + 0.4 * max(dot(normal, normalize(vec3(0.3, 0.5, 1.0))), 0.0);
  colour = vec4(texture(image, uv).rgb * light, 1.0);
}`;

export class Relief {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", { antialias: true });
    this.relief = 0.3; // height of the depth range, as a fraction of the image width
    this.flipped = false;
    this.key = null;
    this.count = 0;
    this.pointers = new Map();
    this.reset();
    if (!this.gl) return;
    this.program = program(this.gl);
    this.buffers = { vertices: this.gl.createBuffer(), indices: this.gl.createBuffer() };
    this.texture = this.gl.createTexture();
    this.listen();
    new ResizeObserver(() => this.draw()).observe(canvas);
  }

  get supported() {
    return Boolean(this.gl);
  }

  reset() {
    this.yaw = -0.35;
    this.tilt = 0.45;
    this.zoom = 1;
    this.draw();
  }

  set(relief, flipped) {
    this.relief = relief;
    this.flipped = flipped;
    this.draw();
  }

  /** Shows the stack at `imageUrl` over the depth map at `depthUrl`, unless already shown. */
  async show(imageUrl, depthUrl) {
    const key = `${imageUrl} ${depthUrl}`;
    if (!this.gl || this.key === key) return;
    this.key = key;
    const [image, depth] = await Promise.all([loadImage(imageUrl), loadImage(depthUrl)]);
    if (this.key !== key) return; // another stack was opened meanwhile
    this.aspect = image.naturalHeight / image.naturalWidth;
    this.mesh(depth);
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, image);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.canvas.style.aspectRatio = `${image.naturalWidth} / ${image.naturalHeight}`;
    this.reset();
  }

  /** A grid of GRID × rows vertices, raised by the depth map (sampled down by the browser). */
  mesh(depth) {
    const columns = GRID;
    const rows = Math.max(2, Math.round(GRID * this.aspect));
    const sampler = document.createElement("canvas");
    sampler.width = columns;
    sampler.height = rows;
    const context = sampler.getContext("2d", { willReadFrequently: true });
    context.imageSmoothingQuality = "high";
    context.drawImage(depth, 0, 0, columns, rows);
    const pixels = context.getImageData(0, 0, columns, rows).data;

    const vertices = new Float32Array(columns * rows * 3);
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < columns; x++) {
        const i = y * columns + x;
        vertices.set([x / (columns - 1), y / (rows - 1), pixels[i * 4] / 255], i * 3);
      }
    }
    const indices = new Uint16Array((columns - 1) * (rows - 1) * 6);
    let n = 0;
    for (let y = 0; y < rows - 1; y++) {
      for (let x = 0; x < columns - 1; x++) {
        const a = y * columns + x;
        const b = a + columns;
        indices.set([a, b, a + 1, a + 1, b, b + 1], n);
        n += 6;
      }
    }
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.vertices);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.buffers.indices);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    this.count = indices.length;
  }

  draw() {
    if (!this.gl || this.pending) return;
    this.pending = requestAnimationFrame(() => {
      this.pending = null;
      this.render();
    });
  }

  render() {
    const { gl, canvas } = this;
    const width = Math.round(canvas.clientWidth * devicePixelRatio);
    const height = Math.round(canvas.clientHeight * devicePixelRatio);
    if (!width || !height) return;
    if (canvas.width !== width || canvas.height !== height) Object.assign(canvas, { width, height });
    gl.viewport(0, 0, width, height);
    gl.clearColor(0.02, 0.024, 0.027, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (!this.count) return;

    gl.useProgram(this.program);
    gl.enable(gl.DEPTH_TEST);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.vertices);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.buffers.indices);
    const vertex = gl.getAttribLocation(this.program, "vertex");
    gl.enableVertexAttribArray(vertex);
    gl.vertexAttribPointer(vertex, 3, gl.FLOAT, false, 0, 0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);

    // Far enough back to fit the whole image, whichever way the canvas is shaped.
    const fit = (0.55 * Math.max(this.aspect, height / width)) / Math.tan(FOV / 2);
    const distance = (fit + this.relief / 2) / this.zoom;
    const uniform = (name) => gl.getUniformLocation(this.program, name);
    gl.uniformMatrix4fv(uniform("view"), false, view(this.yaw, this.tilt, distance));
    gl.uniformMatrix4fv(uniform("projection"), false, perspective(width / height, distance));
    gl.uniform1f(uniform("aspect"), this.aspect);
    gl.uniform1f(uniform("relief"), this.flipped ? -this.relief : this.relief);
    gl.drawElements(gl.TRIANGLES, this.count, gl.UNSIGNED_SHORT, 0);
  }

  listen() {
    const canvas = this.canvas;
    let spread = 0; // distance between two touching fingers
    const gap = () => {
      const [a, b] = [...this.pointers.values()];
      return Math.hypot(a.x - b.x, a.y - b.y);
    };
    canvas.addEventListener("pointerdown", (event) => {
      canvas.setPointerCapture(event.pointerId);
      this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (this.pointers.size === 2) spread = gap();
    });
    canvas.addEventListener("pointermove", (event) => {
      const last = this.pointers.get(event.pointerId);
      if (!last) return;
      const point = { x: event.clientX, y: event.clientY };
      this.pointers.set(event.pointerId, point);
      if (this.pointers.size === 1) {
        const scale = Math.PI / canvas.clientWidth;
        this.yaw += (point.x - last.x) * scale;
        this.tilt = clamp(this.tilt + (point.y - last.y) * scale, -MAX_TILT, MAX_TILT);
      } else if (this.pointers.size === 2) {
        const now = gap();
        this.zoomBy(now / (spread || now));
        spread = now;
      }
      this.draw();
    });
    const release = (event) => this.pointers.delete(event.pointerId);
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        this.zoomBy(Math.exp(-event.deltaY / 500));
        this.draw();
      },
      { passive: false },
    );
    canvas.addEventListener("dblclick", () => this.reset());
  }

  zoomBy(factor) {
    this.zoom = clamp(this.zoom * factor, 0.5, 8);
  }
}

function program(gl) {
  const shader = (type, source) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, source);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const p = gl.createProgram();
  gl.attachShader(p, shader(gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(p, shader(gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  return p;
}

function loadImage(url) {
  const image = new Image();
  image.src = url;
  return image.decode().then(() => image);
}

/** Turn by `yaw` about the vertical, tilt by `tilt`, then step back by `distance`. */
function view(yaw, tilt, distance) {
  const [cy, sy, ct, st] = [Math.cos(yaw), Math.sin(yaw), Math.cos(tilt), Math.sin(tilt)];
  // prettier-ignore
  return new Float32Array([
    cy, st * sy, -ct * sy, 0,
    0, ct, st, 0,
    sy, -st * cy, ct * cy, 0,
    0, 0, -distance, 1,
  ]);
}

function perspective(aspect, distance) {
  const f = 1 / Math.tan(FOV / 2);
  const [near, far] = [distance / 20, distance * 4];
  const range = 1 / (near - far);
  // prettier-ignore
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * range, -1,
    0, 0, 2 * far * near * range, 0,
  ]);
}

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}
