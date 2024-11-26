FROM docker:25.0.5-git

RUN apk update && apk upgrade && apk --no-cache add curl bash make

CMD ["bash"]